from types import SimpleNamespace
from datetime import datetime
from run import run
import ray
from ray import tune, air, train
from ray.tune.trainable import session
from ray.tune.search.optuna import OptunaSearch

def objective(args):
    args["embedding_features"] = args["embedding_features"] * args["num_heads"]
    args["hidden_features"] = args["hidden_features"] * args["num_heads"]
    args = SimpleNamespace(**args)
    session.report({"accuracy": run(args)})

def experiment():
    ray.init(num_gpus=1, num_cpus=1)
    name = datetime.now().strftime("%m%d%Y%H%M%S")
    print(name)

    param_space = {
        "data": tune.choice(["cora"]),
        "hidden_features": tune.randint(1, 32),
        "embedding_features": tune.randint(1, 32),
        "num_heads": tune.randint(1, 32),
        "depth": tune.randint(1, 8),
        "learning_rate": tune.loguniform(1e-4, 1e-2),
        "weight_decay": tune.loguniform(1e-6, 1e-3),
        "patience": tune.randint(5, 10),
        "factor": tune.uniform(0.5, 0.8),
        "num_samples": tune.choice([32]),
        "num_particles": tune.choice([32]),
    }
    
    tune_config = tune.TuneConfig(
        metric="_metric/accuracy",
        mode="max",
        search_alg=OptunaSearch(),
        num_samples=1000,
    )

    run_config = air.RunConfig(
        verbose=0, name=name,
    )

    tuner = tune.Tuner(
        tune.with_resources(objective, {"cpu":1, "gpu": 1}),
        param_space=param_space,
        tune_config=tune_config,
        run_config=run_config,
    )

    results = tuner.fit()

if __name__ == "__main__":
    experiment()
