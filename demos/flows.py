"""Advanced voxel demonstrations composed from the validated core recipes.

These are portable ProcessStep data, not geometry constructors. The public
registry is tcad_simulator.load_demo_flows; constants remain import-compatible.
"""
from __future__ import annotations

from copy import deepcopy


def build_advanced_flows(core):
    """Derive independent recipes without calling the public loader recursively."""
    def variant(source, name, description):
        flow = deepcopy(core[source])
        flow.update(name=name, description=description)
        return flow

    def step(name, label, **params):
        return {"name": name, "instance_name": label, "enabled": True, "params": params}

    def liner(material):
        return step("Deposition", f"10 nm {material} voxel liner", material=material,
                    thickness=10.0, method="ALD", coverage="Full wafer", directionality=0.0)

    sti = variant("Basic Trench", "STI (Shallow Trench Isolation)",
                  "简化浅沟槽隔离：氧化层开窗、硅刻蚀、去胶、理想氧化物填充及CMP；无氮化硅硬掩膜。")
    sti["steps"].extend([
        step("Fill", "Fill isolation trench with oxide", material="Silicon Dioxide",
             max_depth_nm=200.0, direction="top", include_sealed=False),
        step("Deposition", "Oxide overburden", material="Silicon Dioxide",
             thickness=30.0, method="CVD", coverage="Full wafer"),
        step("CMP", "Planarize isolation oxide", target=320.0, pressure=4.0,
             time=60.0, preston=0.5, selectivity_mode="Manual",
             selectivity_pairs=[{"material": "Silicon Dioxide", "ratio": 1.0}]),
    ])

    contact = variant("W Plug + CMP", "Contact Plug (W Fill + CMP)",
                      "四个介质接触孔：光刻开孔、去胶、体素共形TiN阻挡层、理想W填充及CMP。")
    contact["steps"].insert(7, liner("TiN"))
    contact["steps"][-1]["params"]["selectivity_pairs"].append({"material": "TiN", "ratio": 1.0})

    via = deepcopy(contact)
    via.update(name="BEOL Via (Dual Damascene)",
               description="简化单大马士革通孔：四个介质孔、体素TaN衬里、理想Cu填充及CMP；不模拟双大马士革整合。")
    for blob in via["steps"]:
        params = blob["params"]
        if params.get("material") == "TiN":
            params["material"] = "TaN"
            blob["instance_name"] = "10 nm TaN voxel liner"
        if params.get("material") == "Tungsten":
            params["material"] = "Copper"
            blob["instance_name"] = blob["instance_name"].replace("tungsten", "copper")
        if blob["name"] == "CMP":
            blob["instance_name"] = "Polish copper and TaN to oxide stop"
            params["selectivity_pairs"] = [{"material": material, "ratio": 1.0}
                                            for material in ("Copper", "TaN")]

    spacer = variant("Spacer Formation", "Spacer Formation (SADP-like)",
                     "多晶硅芯轴图形化、体素共形氮化硅沉积、方向性回刻、选择性去芯轴，保留两道侧墙。")

    har = variant("Basic Trench", "HAR Trench (DRIE)",
                  "深沟槽几何演示：氧化层开窗后延长硅干法刻蚀；体素速率代理，不模拟Bosch循环或精确HAR输运。")
    har["steps"][0]["params"]["thickness_nm"] = 600.0
    har["steps"][0]["instance_name"] = "600 nm silicon for deep trench"
    for blob in har["steps"]:
        if blob["name"] == "Etch" and blob["params"]["material"] == "Silicon":
            blob["params"].update(time=240.0, selectivity=100.0)
            blob["instance_name"] = "Deep silicon trench dry etch"

    ald = deepcopy(contact)
    ald.update(name="ALD Liner + W Fill",
               description="四个介质孔：体素共形SiN衬里、TiN阻挡层、理想W填充及CMP；ALD为几何近似，不模拟反应动力学。")
    ald["steps"].insert(7, liner("Silicon Nitride"))
    ald["steps"][-1]["params"]["selectivity_pairs"].append({"material": "Silicon Nitride", "ratio": 1.0})

    bond = variant("Bonding + Thinning", "Bond + Flip + Thin",
                   "翻转器件硅晶圆、氧化物键合200 nm硅承载片，再将器件硅减薄至80 nm；简化几何键合。")
    return {flow["name"]: flow for flow in (sti, contact, via, spacer, har, ald, bond)}


def _compatibility_flows():
    from tcad_simulator import MaterialDatabase, _load_core_demo_flows
    return build_advanced_flows(_load_core_demo_flows(MaterialDatabase()))


DEMO_FLOWS = _compatibility_flows()
STI_FLOW = DEMO_FLOWS["STI (Shallow Trench Isolation)"]
CONTACT_PLUG_FLOW = DEMO_FLOWS["Contact Plug (W Fill + CMP)"]
BEOL_VIA_FLOW = DEMO_FLOWS["BEOL Via (Dual Damascene)"]
SPACER_FLOW = DEMO_FLOWS["Spacer Formation (SADP-like)"]
HAR_TRENCH_FLOW = DEMO_FLOWS["HAR Trench (DRIE)"]
ALD_LINER_W_FILL_FLOW = DEMO_FLOWS["ALD Liner + W Fill"]
BOND_THIN_FLOW = DEMO_FLOWS["Bond + Flip + Thin"]
