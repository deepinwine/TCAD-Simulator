# -*- coding: utf-8 -*-
"""M34: Advanced semiconductor demo flow definitions.

每个 flow 是 {name, description, steps: [{name, params}]}，
通过 tcad_simulator.PROCESS_STEP_FACTORIES 反序列化为可执行 ProcessStep。
"""
from __future__ import annotations

from typing import Any, Dict, List


def _flow(name: str, description: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造标准 demo flow dict。"""
    return {
        "name": name,
        "description": description,
        "steps": [
            {"name": s["name"], "enabled": True, "params": s.get("params", {})}
            for s in steps
        ],
    }


# ---- M34 Demo Flows ----

STI_FLOW = _flow(
    "STI (Shallow Trench Isolation)",
    "硅衬底氧化→氮化硅硬掩膜→光刻→各向异性刻蚀Si→氧化物填充→CMP",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "Bulk", "material": "Silicon", "thickness_nm": 500}},
        {"name": "Oxidation/Nitridation", "params": {"temperature": 1000, "time": 300, "thickness_nm": 15}},
        {"name": "Deposition", "params": {"material": "Silicon Nitride", "thickness_nm": 100}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 300}},
        {"name": "Mask Exposure", "params": {"pattern": "Lines", "cd_nm": 200}},
        {"name": "Resist Develop", "params": {"time": 60}},
        {"name": "Etch", "params": {"material": "Silicon Nitride", "chemistry": "Dry", "time": 60}},
        {"name": "Etch", "params": {"material": "Silicon", "chemistry": "Dry", "time": 120}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 400}},
        {"name": "CMP", "params": {"target": 500}},
    ],
)

CONTACT_PLUG_FLOW = _flow(
    "Contact Plug (W Fill + CMP)",
    "硅衬底→氧化层→光刻接触孔→刻蚀→TiN阻挡层→W填充→CMP",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "Bulk", "material": "Silicon", "thickness_nm": 400}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 300}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 250}},
        {"name": "Mask Exposure", "params": {"pattern": "Contacts", "cd_nm": 120}},
        {"name": "Resist Develop", "params": {"time": 60}},
        {"name": "Etch", "params": {"material": "Silicon Dioxide", "chemistry": "Dry", "time": 90}},
        {"name": "Deposition", "params": {"material": "TiN", "thickness_nm": 10}},
        {"name": "Deposition", "params": {"material": "Tungsten", "thickness_nm": 350}},
        {"name": "CMP", "params": {"target": 700}},
    ],
)

BEOL_VIA_FLOW = _flow(
    "BEOL Via (Dual Damascene)",
    "介质沉积→光刻通孔→刻蚀→金属填充→CMP（简化单大马士革）",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "SOI", "material": "Silicon", "thickness_nm": 200}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 500}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 300}},
        {"name": "Mask Exposure", "params": {"pattern": "Vias", "cd_nm": 100}},
        {"name": "Resist Develop", "params": {"time": 60}},
        {"name": "Etch", "params": {"material": "Silicon Dioxide", "chemistry": "Dry", "time": 120}},
        {"name": "Deposition", "params": {"material": "TaN", "thickness_nm": 5}},
        {"name": "Deposition", "params": {"material": "Copper", "thickness_nm": 600}},
        {"name": "CMP", "params": {"target": 700}},
    ],
)

SPACER_FLOW = _flow(
    "Spacer Formation (SADP-like)",
    "芯轴沉积→共形氮化硅→各向异性回刻→去除芯轴→侧墙保留",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "Bulk", "material": "Silicon", "thickness_nm": 400}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 100}},
        {"name": "Deposition", "params": {"material": "Polysilicon", "thickness_nm": 150}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 200}},
        {"name": "Mask Exposure", "params": {"pattern": "Lines", "cd_nm": 80}},
        {"name": "Resist Develop", "params": {"time": 60}},
        {"name": "Etch", "params": {"material": "Polysilicon", "chemistry": "Dry", "time": 60}},
        {"name": "Deposition", "params": {"material": "Silicon Nitride", "thickness_nm": 30}},
        {"name": "Etch", "params": {"material": "Silicon Nitride", "chemistry": "Dry", "time": 30}},
        {"name": "Etch", "params": {"material": "Polysilicon", "chemistry": "Wet", "time": 60}},
    ],
)

HAR_TRENCH_FLOW = _flow(
    "HAR Trench (Deep Reactive Ion Etch)",
    "高深宽比深沟槽刻蚀（Bosch-like 简化模型）",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "Bulk", "material": 1, "thickness_nm": 400}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 200}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 500}},
        {"name": "Mask Exposure", "params": {"pattern": "Lines", "cd_nm": 100}},
        {"name": "Resist Develop", "params": {"time": 90}},
        {"name": "Etch", "params": {"material": 1, "chemistry": "Dry", "time": 300}},
    ],
)

ALD_LINER_W_FILL_FLOW = _flow(
    "ALD Liner + W Fill",
    "深沟槽→ALD SiN衬里→TiN阻挡层→W填充→CMP",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "Bulk", "material": "Silicon", "thickness_nm": 1000}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 200}},
        {"name": "Spin Resist", "params": {"material": "Photoresist", "thickness_nm": 400}},
        {"name": "Mask Exposure", "params": {"pattern": "Contacts", "cd_nm": 80}},
        {"name": "Resist Develop", "params": {"time": 60}},
        {"name": "Etch", "params": {"material": "Silicon", "chemistry": "Dry", "time": 300}},
        {"name": "Deposition", "params": {"material": "Silicon Nitride", "thickness_nm": 8}},
        {"name": "Deposition", "params": {"material": "TiN", "thickness_nm": 5}},
        {"name": "Deposition", "params": {"material": "Tungsten", "thickness_nm": 400}},
        {"name": "CMP", "params": {"target": 1200}},
    ],
)

BOND_THIN_FLOW = _flow(
    "Bond + Flip + Thin",
    "键合第二晶圆→翻转→减薄至停止层",
    [
        {"name": "Initialize Wafer", "params": {"wafer_type": "SOI", "material": "Silicon", "thickness_nm": 725}},
        {"name": "Deposition", "params": {"material": "Silicon Dioxide", "thickness_nm": 50}},
        {"name": "Wafer Flip", "params": {}},
        {"name": "Bonding", "params": {"bond_material": "Silicon Dioxide"}},
        {"name": "Thinning", "params": {"target_thickness_nm": 50, "stop_layer": "Silicon Nitride"}},
    ],
)


DEMO_FLOWS: Dict[str, Dict[str, Any]] = {
    "Basic Trench": None,  # 由 tcad_simulator 内置提供
    "Spacer Formation": None,  # 由 tcad_simulator 内置提供
    "Bonding + Thinning": None,  # 由 tcad_simulator 内置提供
    "W Plug + CMP": None,  # 由 tcad_simulator 内置提供
    "Basic BEOL": None,  # 由 tcad_simulator 内置提供
    "STI (Shallow Trench Isolation)": STI_FLOW,
    "Contact Plug (W Fill + CMP)": CONTACT_PLUG_FLOW,
    "BEOL Via (Dual Damascene)": BEOL_VIA_FLOW,
    "Spacer Formation (SADP-like)": SPACER_FLOW,
    "HAR Trench (DRIE)": HAR_TRENCH_FLOW,
    "ALD Liner + W Fill": ALD_LINER_W_FILL_FLOW,
    "Bond + Flip + Thin": BOND_THIN_FLOW,
}
