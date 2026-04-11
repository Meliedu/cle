"""Contextual bandit for personalized difficulty selection.

Uses a small MLP policy network trained with REINFORCE to select
quiz difficulty (easy / medium / hard) based on a student's
recent performance state vector.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np
import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLD_START_THRESHOLD = 20
STATE_DIM = 10
HIDDEN_DIM = 32
NUM_ACTIONS = 3
LEARNING_RATE = 0.01
ENTROPY_COEFF = 0.01
GRAD_CLIP_NORM = 1.0
REWARD_DECAY = 0.99

DIFFICULTIES: list[str] = ["easy", "medium", "hard"]
_DIFF_INDEX = {d: i for i, d in enumerate(DIFFICULTIES)}
DIFFICULTY_TO_IDX = _DIFF_INDEX  # Public alias for use in API layer


# ---------------------------------------------------------------------------
# Policy network
# ---------------------------------------------------------------------------


class DifficultyPolicy(nn.Module):
    """MLP: STATE_DIM -> HIDDEN_DIM -> NUM_ACTIONS (softmax)."""

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(STATE_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, NUM_ACTIONS),
        )
        self._init_near_uniform()

    def _init_near_uniform(self) -> None:
        """Initialize weights so initial output is near-uniform."""
        for layer in self.net:
            if isinstance(layer, nn.Linear):
                nn.init.xavier_uniform_(layer.weight, gain=0.01)
                nn.init.zeros_(layer.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.net(x)
        return torch.softmax(logits, dim=-1)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def serialize_weights(policy: DifficultyPolicy) -> bytes:
    """Serialize policy weights to bytes for storage (e.g. database BLOB)."""
    buf = io.BytesIO()
    torch.save(policy.state_dict(), buf)
    return buf.getvalue()


def deserialize_weights(blob: bytes) -> DifficultyPolicy:
    """Reconstruct a DifficultyPolicy from a serialized blob."""
    buf = io.BytesIO(blob)
    state_dict = torch.load(buf, map_location="cpu", weights_only=True)
    policy = DifficultyPolicy()
    policy.load_state_dict(state_dict)
    return policy


def create_initial_weights() -> bytes:
    """Return serialized weights for a freshly-initialized policy."""
    return serialize_weights(DifficultyPolicy())


# ---------------------------------------------------------------------------
# State vector computation
# ---------------------------------------------------------------------------


def compute_state_vector(
    attempts: list[Any],
    current_session_count: int,
) -> np.ndarray:
    """Build a 10-dim feature vector from a student's attempt history.

    Features:
      [0-2]: avg score per difficulty (last 50 attempts, default 0.5)
      [3-5]: exponentially decayed recent score per difficulty (last 20)
      [6]:   attempt count / 100, capped at 1.0
      [7]:   streak of consecutive correct from end, /10, capped at 1.0
      [8]:   days since last attempt / 30, capped at 1.0
      [9]:   current_session_count / 20, capped at 1.0
    """
    vec = np.full(STATE_DIM, 0.5, dtype=np.float32)

    if not attempts:
        # Override non-score defaults
        vec[6] = 0.0  # attempt count
        vec[7] = 0.0  # streak
        vec[8] = 0.0  # session gap
        vec[9] = min(current_session_count / 20.0, 1.0)
        return vec

    def _eff_diff(a: Any) -> str:
        return getattr(a, "corrected_difficulty", None) or a.difficulty

    # --- Features 0-2: average score per difficulty (last 50) ---
    recent_50 = attempts[-50:]
    for diff_name, diff_idx in _DIFF_INDEX.items():
        scores = [a.score for a in recent_50 if _eff_diff(a) == diff_name]
        if scores:
            vec[diff_idx] = float(np.mean(scores))
        # else keeps default 0.5

    # --- Features 3-5: exponentially decayed recent score (last 20) ---
    recent_20 = attempts[-20:]
    decay = 0.9
    for diff_name, diff_idx in _DIFF_INDEX.items():
        diff_attempts = [a for a in recent_20 if _eff_diff(a) == diff_name]
        if diff_attempts:
            weighted_sum = 0.0
            weight_total = 0.0
            for i, a in enumerate(diff_attempts):
                w = decay ** (len(diff_attempts) - 1 - i)
                weighted_sum += w * a.score
                weight_total += w
            vec[3 + diff_idx] = weighted_sum / weight_total if weight_total > 0 else 0.5
        else:
            vec[3 + diff_idx] = 0.5

    # --- Feature 6: attempt count normalized ---
    vec[6] = min(len(attempts) / 100.0, 1.0)

    # --- Feature 7: streak of consecutive correct from end ---
    streak = 0
    for a in reversed(attempts):
        if a.score >= 0.8:
            streak += 1
        else:
            break
    vec[7] = min(streak / 10.0, 1.0)

    # --- Feature 8: session gap (days since last attempt) ---
    from datetime import datetime, timezone

    last_time = attempts[-1].created_at
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    gap_days = (now - last_time).total_seconds() / 86400.0
    vec[8] = min(gap_days / 30.0, 1.0)

    # --- Feature 9: session progress ---
    vec[9] = min(current_session_count / 20.0, 1.0)

    return vec


# ---------------------------------------------------------------------------
# Cold-start rule-based selector
# ---------------------------------------------------------------------------


def cold_start_select(recent_history: list[Any]) -> str:
    """Rule-based difficulty selection for students with < COLD_START_THRESHOLD attempts.

    Rules:
      - No history -> medium
      - Last score < 0.5 -> step down
      - Two consecutive >= 0.8 at same difficulty -> step up
      - Otherwise -> stay at current difficulty
    """
    if not recent_history:
        return "medium"

    last = recent_history[-1]
    current_idx = _DIFF_INDEX.get(last.difficulty, 1)

    # Low score -> step down
    if last.score < 0.5:
        return DIFFICULTIES[max(0, current_idx - 1)]

    # Two consecutive high scores at same difficulty -> step up
    if len(recent_history) >= 2:
        prev = recent_history[-2]
        if (
            prev.difficulty == last.difficulty
            and prev.score >= 0.8
            and last.score >= 0.8
        ):
            return DIFFICULTIES[min(NUM_ACTIONS - 1, current_idx + 1)]

    # Stay
    return DIFFICULTIES[current_idx]


# ---------------------------------------------------------------------------
# Degeneracy detection
# ---------------------------------------------------------------------------


def is_degenerate(recent_difficulties: list[str], window: int = 5) -> bool:
    """Check if the policy has collapsed to always picking one difficulty.

    Returns True only when we have at least `window` recent picks and
    they are all the same.
    """
    if len(recent_difficulties) < window:
        return False
    return len(set(recent_difficulties[-window:])) == 1


# ---------------------------------------------------------------------------
# Difficulty selection (main entry point)
# ---------------------------------------------------------------------------


def select_difficulty(
    state: np.ndarray,
    weights: bytes,
    attempt_count: int,
    recent_history: list[Any],
    recent_difficulties: list[str],
) -> tuple[str, float]:
    """Select a difficulty level for the next quiz question.

    Returns (difficulty_string, log_prob).
    Cold-start returns log_prob = 0.0 since no gradient is needed.
    """
    # Cold start path
    if attempt_count < COLD_START_THRESHOLD:
        diff = cold_start_select(recent_history)
        return diff, 0.0

    # Bandit path
    policy = deserialize_weights(weights)
    policy.eval()

    state_tensor = torch.from_numpy(state.astype(np.float32)).unsqueeze(0)

    with torch.no_grad():
        probs = policy(state_tensor).squeeze(0)

    # If degenerate, inject uniform noise to encourage exploration
    if is_degenerate(recent_difficulties):
        uniform = torch.ones(NUM_ACTIONS) / NUM_ACTIONS
        probs = 0.5 * probs + 0.5 * uniform

    dist = torch.distributions.Categorical(probs)
    action = dist.sample()
    log_prob = dist.log_prob(action).item()

    return DIFFICULTIES[action.item()], log_prob


# ---------------------------------------------------------------------------
# REINFORCE policy update
# ---------------------------------------------------------------------------


def update_policy(
    weights: bytes,
    state: np.ndarray,
    chosen_idx: int,
    reward: float,
    reward_mean: float,
    reward_var: float,
    use_normalized_reward: bool = True,
) -> tuple[bytes, float, float]:
    """One-step REINFORCE update.

    Returns (new_weights_blob, new_reward_mean, new_reward_var).
    """
    # --- EMA reward statistics ---
    new_mean = REWARD_DECAY * reward_mean + (1 - REWARD_DECAY) * reward
    new_var = REWARD_DECAY * reward_var + (1 - REWARD_DECAY) * (reward - new_mean) ** 2

    # --- Normalize reward ---
    if use_normalized_reward and new_var > 1e-8:
        adv = (reward - new_mean) / math.sqrt(new_var)
    else:
        adv = reward - new_mean

    # --- Forward pass ---
    policy = deserialize_weights(weights)
    policy.train()

    state_tensor = torch.from_numpy(state.astype(np.float32)).unsqueeze(0)
    probs = policy(state_tensor).squeeze(0)

    dist = torch.distributions.Categorical(probs)
    log_prob = dist.log_prob(torch.tensor(chosen_idx))
    entropy = dist.entropy()

    # --- REINFORCE loss ---
    loss = -(log_prob * adv) - ENTROPY_COEFF * entropy

    # --- SGD step with gradient clipping ---
    optimizer = torch.optim.SGD(policy.parameters(), lr=LEARNING_RATE)
    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(policy.parameters(), GRAD_CLIP_NORM)
    optimizer.step()

    return serialize_weights(policy), float(new_mean), float(new_var)
