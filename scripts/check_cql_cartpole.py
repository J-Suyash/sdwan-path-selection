"""Phase 0 sanity check: train CQL on the CartPole offline dataset.

This mirrors the "d3rlpy CQL example on CartPole" check in milestone M0
of the proposal (Section 14). Keep the budget tiny; we only need to
verify that data loading, training and evaluation work end to end.
"""

from d3rlpy.datasets import get_cartpole
from d3rlpy.algos import DiscreteCQLConfig
from d3rlpy.metrics import EnvironmentEvaluator

import gymnasium


def main() -> None:
    # get_cartpole() returns a legacy gym (0.26) environment that is
    # incompatible with NumPy 2, so we evaluate with a Gymnasium env
    # instead. The dataset itself (4-dim observations, 2 actions) is
    # what we actually train on.
    dataset, _ = get_cartpole()
    env = gymnasium.make("CartPole-v1")
    cql = DiscreteCQLConfig().create(device="cpu")
    cql.fit(
        dataset,
        n_steps=500,
        n_steps_per_epoch=100,
        evaluators={"environment": EnvironmentEvaluator(env)},
    )
    score = EnvironmentEvaluator(env)(cql, dataset)
    print(f"Final mean return over evaluation episodes: {score:.1f}")
    assert score > 0, "CQL should learn a positive return on CartPole"
    print("CQL CartPole check PASSED")


if __name__ == "__main__":
    main()
