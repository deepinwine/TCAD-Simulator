"""Portable fresh Structure CAD demonstration recipes."""


def build_structure_flows():
    def step(name, **params):
        return dict(name='Structure '+name, instance_name='Structure '+name, enabled=True, params=params)
    name = 'Structure CAD — Trench'
    return {name: dict(name=name, description='参数化结构构建：纯几何，无物理仿真；5 nm 体素网格。',
                      domain=dict(grid_shape=[64, 64, 64], voxel_size_nm=5.0, threads=1), steps=[
                          step('Wafer', material='Silicon', thickness_nm=100.0),
                          step('Deposit', material='Silicon Dioxide', thickness_nm=80.0, coverage='Full wafer'),
                          step('Pattern', pattern='Lines', critical_dimension=60.0, pitch=160.0, orientation=0.0),
                          step('Etch', material='Silicon Dioxide', depth_nm=40.0, sidewall_angle_deg=90.0),
                          step('Fill', material='Copper', height_nm=180.0),
                          step('Planarize', height_nm=160.0),
                      ])}
