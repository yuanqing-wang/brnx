from functools import partial, lru_cache
import math
import torch
import dgl
import pyro
from pyro import poutine
from pyro.contrib.gp.models.vsgp import VariationalSparseGP as VSGP
from pyro.contrib.gp.util import conditional
from pyro.nn.module import pyro_method
from pyro import distributions as dist

@lru_cache(maxsize=1)
def graph_exp(graph):
    a = torch.zeros(
        graph.number_of_nodes(),
        graph.number_of_nodes(),
        dtype=torch.float32,
        device=graph.device,
    )
    src, dst = graph.edges()
    a[src, dst] = 1
    d = a.sum(-1, keepdims=True).clamp(min=1)
    a = a / d
    a = a - torch.eye(a.shape[0], dtype=a.dtype, device=a.device)
    a = torch.linalg.matrix_exp(a)
    return a

def graph_conditional(
    X,
    graph,
    iX,
    kernel,
    f_loc,
    f_scale_tril=None,
    Lff=None,
    full_cov=False,
    whiten=False,
    jitter=1e-6,
):
    # N = X.size(0)
    # M = Xnew.size(0)

    A = graph_exp(graph)
    K = kernel(X)
    M = len(iX)
    N = len(X)
    latent_shape = f_loc.shape[:-1]

    if Lff is None:
        Kff = K.contiguous()
        Kff = Kff + torch.eye(Kff.shape[-1], device=Kff.device) * jitter
        Lff = torch.linalg.cholesky(Kff)

    # convert f_loc_shape from latent_shape x N to N x latent_shape
    f_loc = f_loc.permute(-1, *range(len(latent_shape)))
    # convert f_loc to 2D tensor for packing
    f_loc_2D = f_loc.reshape(N, -1)

    # convert f_scale_tril_shape from latent_shape x N x N to N x N x latent_shape
    f_scale_tril = f_scale_tril.permute(-2, -1, *range(len(latent_shape)))
    # convert f_scale_tril to 2D tensor for packing
    f_scale_tril_2D = f_scale_tril.reshape(N, -1)

    if whiten:
        v_2D = f_loc_2D
        W = K
        if f_scale_tril is not None:
            S_2D = f_scale_tril_2D
    else:
        v_2D = torch.linalg.solve_triangular(Lff, f_loc_2D, upper=False)
        W = K
        S_2D = torch.linalg.solve_triangular(Lff, f_scale_tril_2D, upper=False)

    # v_2D = A_inv @ v_2D
    # W = A @ W @ A
    # S_2D = A_inv @ S_2D

    loc_shape = latent_shape + (M,)
    loc = W.matmul(v_2D).t()
    loc = loc @ A
    loc = loc[:, iX]
    loc = loc.reshape(loc_shape)

    W_S_shape = (M,) + f_scale_tril.shape[1:]
    W_S = W.matmul(S_2D)
    W_S = A @ W_S
    W_S = W_S[iX, :]
    W_S = W_S.reshape(W_S_shape)
    # convert W_S_shape from M x N x latent_shape to latent_shape x M x N
    W_S = W_S.permute(list(range(2, W_S.dim())) + [0, 1])

    if full_cov:
        St_Wt = W_S.transpose(-2, -1)
        cov = W_S.matmul(St_Wt)
        return loc, cov

    else:
        var = W_S.pow(2).sum(dim=-1)
        return loc, var



class GraphVariationalSparseGaussianProcess(VSGP):
    def __init__(
        self, 
        graph,
        X,
        y,
        iX,
        kernel, 
        likelihood, 
        hidden_features,
        latent_shape=None,
        jitter=1e-6,
    ):
        super().__init__(
            X=X,
            y=y,
            kernel=kernel,
            Xu=X,
            likelihood=likelihood,
            latent_shape=latent_shape,
            jitter=jitter,
        )
        self.graph = graph
        self.num_inducing_points = graph.number_of_nodes()
        del self.Xu
        self.register_buffer("Xu", X)
        self.register_buffer("iX", iX)
        self.W = torch.nn.Parameter(
            torch.empty(X.shape[-1], hidden_features),
        )
        torch.nn.init.normal_(self.W, std=1.0)

    def set_data(self, X, y):
        self.X = X
        self.y = y

    @pyro_method
    def model(self):
        self.set_mode("model")
        X = self.Xu @ self.W
        X = X.tanh()
        Kuu = self.kernel(X).contiguous()
        a = graph_exp(self.graph)
        Kuu = a @ Kuu @ a.T
        Kuu = Kuu + torch.eye(Kuu.shape[-1], device=Kuu.device) * self.jitter
        Luu = torch.linalg.cholesky(Kuu)
        zero_loc = self.Xu.new_zeros(self.u_loc.shape)
        pyro.sample(
            self._pyro_get_fullname("u"),
            dist.MultivariateNormal(zero_loc, scale_tril=Luu).to_event(
                zero_loc.dim() - 1
            ),
        )
        f_loc, f_var = graph_conditional(
            X=self.Xu@self.W,
            graph=self.graph,
            iX=self.iX,
            kernel=self.kernel, 
            f_loc=self.u_loc, 
            f_scale_tril=self.u_scale_tril, 
            full_cov=False, 
            jitter=self.jitter, 
        )
        self.likelihood._load_pyro_samples()
        # f_loc = f_loc + (self.X[self.iX, :] @ self.W_mean).T
        return self.likelihood(f_loc, f_var, self.y)

    def forward(self, iX, full_cov=False):
        self.set_mode("guide")
        loc, cov = graph_conditional(
            X=self.Xu@self.W,
            graph=self.graph,
            iX=iX,
            kernel=self.kernel,
            f_loc=self.u_loc,
            f_scale_tril=self.u_scale_tril,
            full_cov=full_cov,
            jitter=self.jitter,
        )
        # loc = loc + (X[iX, :] @ self.W_mean).T
        return loc, cov
        




        


