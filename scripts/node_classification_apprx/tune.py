from types import SimpleNamespace
from datetime import datetime
from run import run
import ray
from ray import tune, air, train
from ray.tune.trainable import session
from ray.tune.search.ax import AxSearch

def multiply_by_heads(args):
    args["embedding_features"] = (
        args["embedding_features"] * args["num_heads"]
    )
    args["hidden_features"] = args["hidden_features"] * args["num_heads"]
    return args

def objective(args):
    args = multiply_by_heads(args)
    args = SimpleNamespace(**args)
    accuracy = sum([run(args) for _ in range(3)]) / 3
    session.report({"accuracy": accuracy})

def experiment(args):
    ray.init(num_gpus=1, num_cpus=1)
    name = datetime.now().strftime("%m%d%Y%H%M%S")
    print(name) 

    param_space = {
        "data": tune.choice([args.data]),
        "hidden_features": tune.randint(4, 16),
        "embedding_features": tune.randint(4, 16),
        "num_heads": tune.randint(4, 32),
        "depth": tune.randint(2, 15),
        "learning_rate": tune.loguniform(1e-4, 1e-2),
        "weight_decay": tune.loguniform(1e-5, 1e-3),
        "num_samples": tune.choice([16]),
        "num_particles": tune.choice([16]),
        "sigma_factor": tune.uniform(0.5, 10.0),
        "t": tune.uniform(0.5, 15.0),
        "gamma": tune.uniform(-1.0, 0.0),
        "optimizer": tune.choice(["RMSprop"]),
        "edge_recover_scale": tune.loguniform(1e-5, 1e-2),
        "node_recover_scale": tune.loguniform(1e-5, 1e-2),
        "kl_scale": tune.loguniform(1e-5, 1e-2),
        "alpha": tune.uniform(0.1, 1.0),
        "swa_start": tune.randint(10, 30),
        "swa_lr": tune.loguniform(1e-4, 1e-2),
        "swa_freq": tune.randint(5, 15),
        "n_epochs": tune.randint(50, 100),
        "test": tune.choice([0]),
    }

    tune_config = tune.TuneConfig(
        metric="_metric/accuracy",
        mode="max",
        search_alg=AxSearch(),
        num_samples=500,
    )

    run_config = air.RunConfig(
        verbose=0,
        name=name,
        storage_path=args.data,
        stop={"time_total_s": 100},
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