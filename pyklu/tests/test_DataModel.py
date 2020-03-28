import os
import unittest
import numpy as np
import pdb
from scipy import sparse
from pyklu_cpp import DataModel, PandaPowerConverter
import pandapower.networks as pn
import pandapower as pp


class MakeTests(unittest.TestCase):
    def setUp(self):
        self.net_ref = pn.case118()
        self.net_datamodel = pn.case118()

        # initialize constant stuff
        self.max_it = 10
        self.tol = 1e-8  # tolerance for the solver
        self.tol_test = 1e-5  # tolerance for the test (2 matrices are equal if the l_1 of their difference is less than this)

        # initialize and use converters
        self.converter = PandaPowerConverter()
        self.converter.set_sn_mva(self.net_datamodel.sn_mva)  # TODO raise an error if not set !
        self.converter.set_f_hz(self.net_datamodel.f_hz)
        self.line_r, self.line_x, self.line_h = \
            self.converter.get_line_param(
                self.net_datamodel.line["r_ohm_per_km"].values * self.net_datamodel.line["length_km"].values,
                self.net_datamodel.line["x_ohm_per_km"].values * self.net_datamodel.line["length_km"].values,
                self.net_datamodel.line["c_nf_per_km"].values * self.net_datamodel.line["length_km"].values,
                self.net_datamodel.line["g_us_per_km"].values * self.net_datamodel.line["length_km"].values,
                self.net_datamodel.bus.loc[self.net_datamodel.line["from_bus"]]["vn_kv"],
                self.net_datamodel.bus.loc[self.net_datamodel.line["to_bus"]]["vn_kv"]
            )
        self.trafo_r, self.trafo_x, self.trafo_b = \
            self.converter.get_trafo_param(self.net_datamodel.trafo["vn_hv_kv"].values,
                                           self.net_datamodel.trafo["vn_lv_kv"].values,
                                           self.net_datamodel.trafo["vk_percent"].values,
                                           self.net_datamodel.trafo["vkr_percent"].values,
                                           self.net_datamodel.trafo["sn_mva"].values,
                                           self.net_datamodel.trafo["pfe_kw"].values,
                                           self.net_datamodel.trafo["i0_percent"].values,
                                           self.net_datamodel.bus.loc[self.net_datamodel.trafo["lv_bus"]]["vn_kv"]
                                           )

        # set up the data model accordingly
        self.model = DataModel()
        tmp_bus_ind = np.argsort(self.net_datamodel.bus.index)
        self.model.init_bus(self.net_datamodel.bus.iloc[tmp_bus_ind]["vn_kv"].values,
                            self.net_datamodel.line.shape[0],
                            self.net_datamodel.trafo.shape[0])

        self.model.init_powerlines(self.line_r, self.line_x, self.line_h,
                                   self.net_datamodel.line["from_bus"].values,
                                   self.net_datamodel.line["to_bus"].values
                                   )

        # init the shunts
        self.model.init_shunt(self.net_datamodel.shunt["p_mw"].values,
                              self.net_datamodel.shunt["q_mvar"].values,
                              self.net_datamodel.shunt["bus"].values
                              )

        tap_step_pct = self.net_datamodel.trafo["tap_step_percent"].values
        tap_step_pct[~np.isfinite(tap_step_pct)] = 0.

        tap_pos = self.net_datamodel.trafo["tap_pos"].values
        tap_pos[~np.isfinite(tap_pos)] = 0.

        is_tap_hv_side = self.net_datamodel.trafo["tap_side"].values == "hv"
        is_tap_hv_side[~np.isfinite(tap_pos)] = True
        self.model.init_trafo(self.trafo_r,
                              self.trafo_x,
                              self.trafo_b,
                              tap_step_pct,
                              tap_pos,
                              is_tap_hv_side,
                              self.net_datamodel.trafo["hv_bus"].values,
                              self.net_datamodel.trafo["lv_bus"].values)

        self.model.init_loads(self.net_datamodel.load["p_mw"].values,
                              self.net_datamodel.load["q_mvar"].values,
                              self.net_datamodel.load["bus"].values
                              )
        self.model.init_generators(self.net_datamodel.gen["p_mw"].values,
                                   self.net_datamodel.gen["vm_pu"].values,
                                   self.net_datamodel.gen["bus"].values
                                   )

        # TODO handle that better maybe
        self.model.add_slackbus(self.net_datamodel.ext_grid["bus"].values[0])

    def assert_equal(self, tmp, ref):
        assert np.all(tmp.shape == ref.shape), "vector does not have the same shape"
        assert np.max(np.abs(tmp - ref)) <= self.tol_test
        assert np.mean(np.abs(tmp - ref)) <= self.tol_test

    def check_res(self, net):
        # check lines
        l_is = self.net_ref.line["in_service"]
        por, qor, vor, aor = self.model.get_lineor_res()
        self.assert_equal(por, net.res_line["p_from_mw"].values)
        self.assert_equal(qor, net.res_line["q_from_mvar"].values)
        self.assert_equal(aor, net.res_line["i_from_ka"].values)
        vor_pp = net.bus.loc[net.line["from_bus"].values]["vn_kv"].values * net.res_line["vm_from_pu"].values
        self.assert_equal(vor[l_is], vor_pp[l_is])

        # check trafo
        f_is = self.net_ref.trafo["in_service"]
        plv, qlv, vlv, alv = self.model.get_trafolv_res()
        self.assert_equal(plv, net.res_trafo["p_lv_mw"].values)
        self.assert_equal(qlv, net.res_trafo["q_lv_mvar"].values)
        self.assert_equal(alv, net.res_trafo["i_lv_ka"].values)
        vlv_pp = net.bus.loc[net.trafo["lv_bus"].values]["vn_kv"].values * net.res_trafo["vm_lv_pu"].values
        self.assert_equal(vlv[f_is], vlv_pp[f_is])

        # check loads
        l_is = self.net_ref.load["in_service"]
        load_p, load_q, load_v = self.model.get_loads_res()
        self.assert_equal(load_p[l_is], net.res_load["p_mw"].values[l_is])
        self.assert_equal(load_q[l_is], net.res_load["q_mvar"].values[l_is])

        # check shunts
        s_is = self.net_ref.shunt["in_service"]
        shunt_p, shunt_q, shunt_v = self.model.get_shunts_res()
        self.assert_equal(shunt_p[s_is], net.res_shunt["p_mw"].values[s_is])
        self.assert_equal(shunt_q[s_is], net.res_shunt["q_mvar"].values[s_is])

        # check generators
        g_is = self.net_ref.gen["in_service"]
        prod_p, prod_q, prod_v = self.model.get_gen_res()
        self.assert_equal(prod_p[g_is], net.res_gen["p_mw"].values[g_is])
        # self.assert_equal(prod_q, net.res_gen["q_mvar"].values)
        v_gen_pp = net.bus.loc[net.gen["bus"].values]["vn_kv"].values * net.res_gen["vm_pu"].values
        self.assert_equal(prod_v[g_is], v_gen_pp[g_is])

    def make_v0(self, net):
        V0 = np.full(net.bus.shape[0],
                     fill_value=1.0,
                     dtype=np.complex_)
        all_gen_conn = net.gen["bus"].values
        g_is = net.gen["in_service"].values
        V0[all_gen_conn[g_is]] *= self.net_datamodel.gen.iloc[g_is]["vm_pu"].values
        V0[net.ext_grid["bus"].values] = net.ext_grid["vm_pu"].values * np.exp(
            1j * net.ext_grid["va_degree"].values / 360. * 2 * np.pi)
        return V0

    def test_acpf(self):
        """
        Reference without modifying anything
        """
        # compute a powerflow on a net without anything
        pp.runpp(self.net_ref, init="flat")

        V0 = self.make_v0(self.net_ref)
        V0_th = np.array([0.955     +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.01      +0.j    ,
                       0.971     +0.j    , 0.965     +0.j    , 1.        +0.j    ,
                       0.952     +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.973     +0.j    , 0.99      +0.j    , 0.98      +0.j    ,
                       0.975     +0.j    , 0.993     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.005     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.97      +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.973     +0.j    , 0.962     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 0.992     +0.j    , 1.05      +0.j    ,
                       1.015     +0.j    , 0.968     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 0.998     +0.j    ,
                       0.967     +0.j    , 0.963     +0.j    , 1.        +0.j    ,
                       0.984     +0.j    , 1.        +0.j    , 0.98      +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.97      +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.985     +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.005     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.025     +0.j    , 1.        +0.j    ,
                       0.99      +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 0.955     +0.j    , 0.952     +0.j    ,
                       0.954     +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.985     +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       0.995     +0.j    , 0.998     +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.005     +0.j    , 1.05      +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 0.89633629+0.5175j,
                       0.984     +0.j    , 1.015     +0.j    , 1.        +0.j    ,
                       0.98      +0.j    , 0.991     +0.j    , 0.958     +0.j    ,
                       1.        +0.j    , 0.943     +0.j    , 1.006     +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.04      +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 0.985     +0.j    ,
                       1.        +0.j    , 1.015     +0.j    , 1.        +0.j    ,
                       1.005     +0.j    , 0.985     +0.j    , 1.05      +0.j    ,
                       0.98      +0.j    , 0.99      +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.        +0.j    ,
                       1.        +0.j    , 1.        +0.j    , 1.01      +0.j    ,
                       1.017     +0.j    ])
        # V0_th = V0[tmp_bus_ind]
        # pdb.set_trace()
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_disco_gen(self):
        self.net_ref.gen["in_service"][0] = False
        self.model.deactivate_gen(0)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_disco_load(self):
        self.net_ref.load["in_service"][0] = False
        self.model.deactivate_load(0)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_disco_line(self):
        self.net_ref.line["in_service"][0] = False
        self.model.deactivate_powerline(0)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_disco_shunt(self):
        self.net_ref.shunt["in_service"][0] = False
        self.model.deactivate_shunt(0)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_disco_trafo(self):
        self.net_ref.trafo["in_service"][0] = False
        self.model.deactivate_trafo(0)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_reactivate(self):
        # i deactivate everything, run a powerflow, and check that reactivating everything and supposes that the results
        # is the same
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)

        # i disconnect a load, the reconnect it
        self.model.deactivate_load(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.model.reactivate_load(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

        self.model.deactivate_gen(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.model.reactivate_gen(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

        self.model.deactivate_powerline(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.model.reactivate_powerline(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

        self.model.deactivate_trafo(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.model.reactivate_trafo(0)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_gen(self):
        self.net_ref.gen["bus"][0] = 2
        self.model.change_bus_gen(0, 2)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_load(self):
        self.net_ref.load["bus"][0] = 2
        self.model.change_bus_load(0, 2)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_shunt(self):
        self.net_ref.shunt["bus"][0] = 2
        self.model.change_bus_shunt(0, 2)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_lineor(self):
        self.net_ref.line["from_bus"][0] = 2
        self.model.change_bus_powerline_or(0, 2)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_lineex(self):
        self.net_ref.line["to_bus"][0] = 2
        self.model.change_bus_powerline_ex(0, 2)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_trafolv(self):
        self.net_ref.trafo["lv_bus"][0] = 5  # was 4 initially, and 4 is connected to 5
        self.model.change_bus_trafo_lv(0, 5)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)

    def test_acpf_changebus_trafohv(self):
        self.net_ref.trafo["hv_bus"][0] = 29  # was 7 initially, and 7 is connected to 29
        self.model.change_bus_trafo_hv(0, 29)
        pp.runpp(self.net_ref, init="flat")
        V0 = self.make_v0(self.net_ref)
        has_conv = self.model.compute_newton(V0, self.max_it, self.tol)
        assert has_conv, "powerflow diverged !"
        self.check_res(self.net_ref)


if __name__ == "__main__":
    unittest.main()