"""Token-rate pacing for sequential provider runs.

The `l1_pilot_002` run issued all twelve cases back to back. Each case costs
roughly 4,200 tokens and a call returns in about 1.6 seconds, so the run
generated 8,347 tokens in 8.2 seconds -- about 60,000 tokens per minute against
a Groq ``on_demand`` ceiling of 8,000. Ten of the twelve cases were rejected
before inference with a rate-limit error, and nothing about the pilot's own
behaviour was at fault: it simply asked for far more than the account was
allowed to answer per minute.

Serialising the cases does not fix that, and this is the point worth being blunt
about. The cases were *already* sequential; the burst came from each one being
quick, not from them overlapping. A fixed ``time.sleep`` between cases is the
usual answer and is worse than useless here: it would add minutes of dead time
on an account with headroom, while still being wrong the moment a case costs
more than assumed.

So the wait is computed rather than guessed. This tracks what has actually been
consumed inside the provider's rolling window, reserves room for the work about
to be issued, and sleeps for exactly as long as it takes for the oldest tokens
to age out -- and not at all when there is room. The estimate it reserves
against is learned from the run's own observed per-case cost, so it tightens as
the pilot goes instead of being a guess frozen at the start.
"""

import os
import time
from typing import Callable, List, Optional, Tuple

#: Tokens-per-minute ceiling to plan against.
#:
#: 8,000 is what Groq reported for the ``on_demand`` tier on
#: ``openai/gpt-oss-120b``. It is a property of the provider's account, not of
#: this code, so it is overridable rather than baked in; a different provider or
#: a higher tier needs no edit here.
DEFAULT_TPM_LIMIT = 8000

#: The provider's rate-limit window. Groq's is one minute.
DEFAULT_WINDOW_SECONDS = 60.0

#: Fraction of the limit the pacer will plan to use.
#:
#: Kept below 1.0 so a run that lands exactly on the ceiling is not rejected for
#: using what it was permitted to use. The margin also absorbs the estimate
#: being slightly low.
DEFAULT_SAFETY_FRACTION = 0.85

#: Tokens assumed for the first case, before any has been observed.
#:
#: A case is three calls -- teaching turn, checkpoint, feedback -- measured at
#: about 1,400 tokens each in the live run. Deliberately rounded up.
DEFAULT_CASE_TOKEN_ESTIMATE = 5_000


def tpm_limit_from_env(default: int = DEFAULT_TPM_LIMIT) -> int:
    """Return the configured TPM ceiling, or *default*.

    Read from the environment rather than from a constant so that raising a rate
    limit, or pointing the pacer at a different provider, needs no code change.
    """
    raw = os.environ.get("EKAGRA_PILOT_TPM_LIMIT", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class TokenPacer:
    """Reserve room in a provider's token window before issuing work.

    The clock and the sleeper are injected so that tests can drive the pacer
    through a full window without waiting a real minute.
    """

    def __init__(
        self,
        tpm_limit: int = DEFAULT_TPM_LIMIT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        safety_fraction: float = DEFAULT_SAFETY_FRACTION,
        clock: Optional[Callable[[], float]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ):
        self.tpm_limit = max(1, int(tpm_limit))
        self.window_seconds = float(window_seconds)
        self.safety_fraction = min(1.0, max(0.01, float(safety_fraction)))
        self._clock = clock if clock is not None else time.monotonic
        self._sleep = sleeper if sleeper is not None else time.sleep
        # (timestamp, tokens) pairs still inside the window.
        self._events: List[Tuple[float, int]] = []
        # Largest per-case cost seen, used as the reservation from then on.
        self._observed_case_tokens = 0
        self.waited_seconds = 0.0
        self.waits = 0

    # -- accounting -------------------------------------------------------

    @property
    def effective_limit(self) -> int:
        """Return the ceiling the pacer actually plans against."""
        return int(self.tpm_limit * self.safety_fraction)

    def _prune(self, now: Optional[float] = None) -> int:
        """Drop events that have aged out, returning tokens still in the window."""
        now = self._clock() if now is None else now
        cutoff = now - self.window_seconds
        self._events = [e for e in self._events if e[0] > cutoff]
        return sum(tokens for _, tokens in self._events)

    def tokens_in_window(self) -> int:
        """Return the tokens consumed inside the current window."""
        return self._prune()

    def observe(self, tokens: int, at: Optional[float] = None) -> None:
        """Record *tokens* as consumed at *at* (default: now)."""
        if tokens <= 0:
            return
        self._events.append((self._clock() if at is None else at, int(tokens)))
        self._prune()

    def note_case_tokens(self, tokens: int) -> None:
        """Record what a whole case cost, so the next reservation can use it."""
        if tokens > self._observed_case_tokens:
            self._observed_case_tokens = int(tokens)

    @property
    def reservation(self) -> int:
        """Return the tokens to reserve for the next case.

        Learned from the run so far, never below the initial estimate, so a
        quiet first case cannot convince the pacer that every case is quiet.
        """
        return max(DEFAULT_CASE_TOKEN_ESTIMATE, self._observed_case_tokens)

    # -- pacing -----------------------------------------------------------

    def wait_for_capacity(self, needed_tokens: Optional[int] = None) -> float:
        """Block until *needed_tokens* fit in the window. Return seconds slept.

        Returns 0.0 immediately when there is room, which is the common case on a
        generous limit and the case that keeps a dry run instant.
        """
        needed = self.reservation if needed_tokens is None else int(needed_tokens)
        if needed <= 0:
            return 0.0
        slept = 0.0
        # Bounded: each pass either returns or ages tokens out, and the window
        # bounds how many passes that can take.
        for _ in range(64):
            now = self._clock()
            in_window = self._prune(now)
            if in_window + needed <= self.effective_limit:
                if slept:
                    self.waited_seconds += slept
                    self.waits += 1
                return slept
            wait = self._seconds_until_room(in_window, needed, now)
            if wait <= 0:
                # Cannot make room by waiting (the reservation alone exceeds the
                # ceiling). Wait the window out once so the next case starts
                # clean rather than failing immediately against a full window.
                wait = self.window_seconds
            self._sleep(wait)
            slept += wait
        self.waited_seconds += slept
        self.waits += 1
        return slept

    def _seconds_until_room(self, in_window: int, needed: int, now: float) -> float:
        """Return how long until enough of the window's tokens have aged out."""
        overflow = in_window + needed - self.effective_limit
        if overflow <= 0:
            return 0.0
        oldest_first = sorted(self._events, key=lambda e: e[0])
        released = 0
        for timestamp, tokens in oldest_first:
            released += tokens
            if released >= overflow:
                # Tokens stop counting once they are a full window old.
                return max(0.0, (timestamp + self.window_seconds) - now)
        return self.window_seconds


__all__ = [
    "DEFAULT_CASE_TOKEN_ESTIMATE",
    "DEFAULT_SAFETY_FRACTION",
    "DEFAULT_TPM_LIMIT",
    "DEFAULT_WINDOW_SECONDS",
    "TokenPacer",
    "tpm_limit_from_env",
]