import os
import unittest
import copy
import numpy as np
import pdb
from scipy import sparse
from lightsim2grid.initGridModel import init
import pandapower.networks as pn
import pandapower as pp

from test_GridModel import BaseTests


class MakeACTestsDisco(BaseTests, unittest.TestCase):
    def setUp(self):
        self.net = pn.case118()
        self.last_real_bus = self.net.bus.shape[0]
        pp.create_bus(self.net, vn_kv=self.net.bus["vn_kv"][0])
        self.net.bus["in_service"][self.last_real_bus] = False
        self.net_ref = copy.deepcopy(self.net)
        self.net_datamodel = copy.deepcopy(self.net)
        self.n_bus = self.net.bus.shape[0]
        self.model = init(self.net)
        self.model.deactivate_bus(self.last_real_bus)

        self.max_it = 10
        self.tol = 1e-8  # tolerance for the solver
        self.tol_test = 1e-5  # tolerance for the test (2 matrices are equal if the l_1 of their difference is less than this)

    def run_me_pf(self, V0):
        return self.model.ac_pf(V0, self.max_it, self.tol)

    def run_ref_pf(self, net):
        pp.runpp(net, init="flat")

    def do_i_skip(self, test_nm):
        return


class MakeDCTestsDisco(BaseTests, unittest.TestCase):
    def setUp(self):
        self.net = pn.case118()
        self.last_real_bus = self.net.bus.shape[0]
        pp.create_bus(self.net, vn_kv=self.net.bus["vn_kv"][0])
        self.net.bus["in_service"][self.last_real_bus] = False
        self.net_ref = copy.deepcopy(self.net)
        self.net_datamodel = copy.deepcopy(self.net)
        self.n_bus = self.net.bus.shape[0]
        self.model = init(self.net)
        self.model.deactivate_bus(self.last_real_bus)

        self.max_it = 10
        self.tol = 1e-8  # tolerance for the solver
        self.tol_test = 1e-5  # tolerance for the test (2 matrices are equal if the l_1 of their difference is less than this)

    def run_me_pf(self, V0):
        return self.model.dc_pf(V0, self.max_it, self.tol)

    def run_ref_pf(self, net):
        pp.rundcpp(net, init="flat")

    def do_i_skip(self, test_nm):
        pass

    def check_res(self, Vfinal, net):
        assert Vfinal.shape[0] > 0, "powerflow diverged !"
        tmp_bus_ind = np.argsort(net.bus.index)
        tmp_bus_ind = tmp_bus_ind[tmp_bus_ind != self.last_real_bus]
        va_deg = net.res_bus["va_degree"].values
        self.assert_equal(np.angle(Vfinal)[:self.last_real_bus], va_deg[tmp_bus_ind] / 180. * np.pi)


if __name__ == "__main__":
    unittest.main()