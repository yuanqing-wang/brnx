import ray
from ray.tune import ExperimentAnalysis

def run(path):
    analysis = ExperimentAnalysis(path)
    trial = analysis.get_best_trial("_metric/accuracy", "max")    
    accuracy = analysis.results[trial.trial_id]["_metric"]["accuracy"]
    print(accuracy)

if __name__ == "__main__":
    import sys
    run(sys.argv[1])
