from types import SimpleNamespace
from datetime import datetime
from run import run
import ray
from ray import tune, air, train
from ray.tune.trainable import session
from ray.tune.search.optuna import OptunaSearch

def multiply_by_heads(args):
    args["embedding_features"] = (
        args["embedding_features"] * args["num_heads"]
    )
    args["hidden_features"] = args["hidden_features"] * args["num_heads"]
    return args

def objective(args):
    args = multiply_by_heads(args)
    args = SimpleNamespace(**args)
    accuracy, accuracy_te = run(args)
    session.report({"accuracy": accuracy, "accuracy_te": accuracy_te})

def experiment(args):
    ray.init(num_gpus=1, num_cpus=1)
    name = datetime.now().strftime("%m%d%Y%H%M%S")
    print(name)

    param_space = {
        "data": tune.choice([args.data]),
        "hidden_features": tune.randint(8, 32),
        "embedding_features": tune.randint(8, 32),
        "num_heads": tune.randint(4, 32),
        "depth": tune.randint(1, 8),
        "learning_rate": tune.loguniform(1e-3, 5e-2),
        "weight_decay": tune.loguniform(1e-4, 1e-2),
        "patience": tune.randint(5, 10),
        "factor": tune.uniform(0.5, 1.0),
        "num_samples": tune.choice([8]),
        "num_particles": tune.choice([8]),
        "sigma_factor": tune.uniform(1.0, 10.0),
    }

    tune_config = tune.TuneConfig(
        metric="_metric/accuracy",
        mode="max",
        search_alg=OptunaSearch(),
        num_samples=1000,
    )

    run_config = air.RunConfig(
        # verbose=0,
        name=name,
        local_dir=args.data,
    )

    tuner = tune.Tuner(
        tune.with_resources(objective, {"cpu": 1, "gpu": 1}),
        param_space=param_space,
        tune_config=tune_config,
        run_config=run_config,
    )

    results = tuner.fit()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="CoraGraphDataset")
    args = parser.parse_args()
    experiment(args)
