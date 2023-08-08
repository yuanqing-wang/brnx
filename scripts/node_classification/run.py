import numpy as np
import torch
import gpytorch
# gpytorch.settings.debug._default = False
gpytorch.settings.lazily_evaluate_kernels._default = False
import linear_operator
# linear_operator.settings.cholesky_jitter._global_float_value = 1e-4
# linear_operator.settings.cholesky_jitter._global_double_value = 1e-4

import dgl
from ogb.nodeproppred import DglNodePropPredDataset
dgl.use_libxsmm(False)

def run(args):
    torch.cuda.empty_cache()
    from dgl.data import (
        CoraGraphDataset,
        CiteseerGraphDataset,
        PubmedGraphDataset,
        CoauthorCSDataset,
        CoauthorPhysicsDataset,
        AmazonCoBuyComputerDataset,
        AmazonCoBuyPhotoDataset,
    )

    g = locals()[args.data](verbose=False)[0]
    g = dgl.remove_self_loop(g)
    g = dgl.add_self_loop(g)

    if "train_mask" not in g.ndata:
        g.ndata["train_mask"] = torch.zeros(g.number_of_nodes(), dtype=torch.bool)
        g.ndata["val_mask"] = torch.zeros(g.number_of_nodes(), dtype=torch.bool)
        g.ndata["test_mask"] = torch.zeros(g.number_of_nodes(), dtype=torch.bool)

        train_idxs = torch.tensor([], dtype=torch.int32)
        val_idxs = torch.tensor([], dtype=torch.int32)
        test_idxs = torch.tensor([], dtype=torch.int32)

        n_classes = g.ndata["label"].shape[-1]
        for idx_class in range(n_classes):
            idxs = torch.where(g.ndata["label"][:, idx_class] == 1)[0]
            assert len(idxs) > 50
            idxs = idxs[torch.randperm(len(idxs))]
            _train_idxs = idxs[:20]
            _val_idxs = idxs[20:50]
            _test_idxs = idxs[50:]
            train_idxs = torch.cat([train_idxs, _train_idxs])
            val_idxs = torch.cat([val_idxs, _val_idxs])
            test_idxs = torch.cat([test_idxs, _test_idxs])

        g.ndata["train_mask"][train_idxs] = True
        g.ndata["val_mask"][val_idxs] = True
        g.ndata["test_mask"][test_idxs] = True

    from bronx.models import BronxModel, ExactBronxModel
    if torch.cuda.is_available():
        g = g.to("cuda:0")

    likelihood = gpytorch.likelihoods.DirichletClassificationLikelihood(
        targets=g.ndata["label"][g.ndata["train_mask"]],
        learn_additional_noise=False,
    )

    model = ExactBronxModel(
        train_x=torch.where(g.ndata["train_mask"])[0],
        train_y=likelihood.transformed_targets,
        likelihood=likelihood,
        num_classes=likelihood.num_classes,
        features=g.ndata["feat"],
        graph=g,
    )

    if torch.cuda.is_available():
        model = model.to("cuda:0")
        likelihood = likelihood.cuda()


    mll = gpytorch.mlls.ExactMarginalLogLikelihood(likelihood, model)

    # optimizer = getattr(
    #     torch.optim, args.optimizer
    # )(list(model.hyperparameters()) + list(likelihood.parameters()), lr=args.learning_rate)

    # ngd = gpytorch.optim.NGD(model.variational_parameters(), num_data=g.ndata["train_mask"].sum(), lr=0.01)
    
    optimizer = getattr(
        torch.optim, args.optimizer
    )(
        list(model.hyperparameters()) + list(likelihood.parameters()), 
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
    )

    for idx in range(args.n_epochs):
        model.train()
        likelihood.train()
        optimizer.zero_grad()
        output = model(torch.where(g.ndata["train_mask"])[0])
        loss = -mll(output, target=likelihood.transformed_targets)
        loss = loss.sum()
        loss.backward()
        optimizer.step()

    with torch.no_grad():
        model.eval()
        likelihood.eval()
        y_hat = model(torch.where(g.ndata["val_mask"])[0]).loc
        y = g.ndata["label"][g.ndata["val_mask"]]
        accuracy = (y_hat.argmax(dim=0) == y).float().mean()
        print(accuracy)



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="CoraGraphDataset")
    parser.add_argument("--hidden_features", type=int, default=16)
    parser.add_argument("--embedding_features", type=int, default=64)
    parser.add_argument("--learning_rate", type=float, default=1e-3)
    parser.add_argument("--weight_decay", type=float, default=1e-10)
    parser.add_argument("--optimizer", type=str, default="Adam")
    parser.add_argument("--n_epochs", type=int, default=5)
    parser.add_argument("--test", type=int, default=1)
    args = parser.parse_args()
    run(args)
