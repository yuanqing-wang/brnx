from functools import lru_cache, partial
import torch
from pyro.contrib.gp.kernels.kernel import Kernel
# from pyro.contrib.gp.util import conditional as _conditional

class GraphLinearDiffusion(Kernel):
    def __init__(self, input_dim, variance=None, active_dims=None):
        super().__init__(input_dim, active_dims)

    @lru_cache(maxsize=1)
    def graph_exp(self, graph):
        # a = graph.adj().to_dense()
        a = torch.zeros(
            graph.number_of_nodes(), graph.number_of_nodes(),
            dtype=torch.float32, device=graph.device,
        )
        src, dst = graph.edges()
        a[src, dst] = 1
        d = a.sum(-1, keepdims=True).clamp(min=1)
        a = a / d
        a = a - torch.eye(a.shape[0], dtype=a.dtype, device=a.device)
        a = torch.linalg.matrix_exp(a)
        return a

    @lru_cache(maxsize=8)
    def forward(self, graph, X, Z=None, diag=False):
        if Z is None:
            Z = X
        variance = self.graph_exp(graph)
        variance = variance[X.long(), :][:, Z.long()]
        if diag:
            variance = variance.diag()
        return variance

class CombinedGraphDiffusion(Kernel):
    def __init__(
            self, input_dim, variance=None, active_dims=None, 
            base_kernel=None,
        ):
        super().__init__(input_dim, active_dims)
        self.graph_diffusion_kernel = GraphLinearDiffusion(input_dim)
        self.base_kernel = base_kernel

    def forward(self, X, Z=None, graph=None, iX=None, iZ=None, diag=False):
        assert graph is not None
        assert iX is not None
        if Z is None:
            Z = X
        if iZ is None:
            iZ = iX

        variance = self.graph_diffusion_kernel(graph, iX, iZ, diag)
        if self.base_kernel is not None:
            variance = variance * self.base_kernel(X, Z, diag)
        return variance

    





        
        


