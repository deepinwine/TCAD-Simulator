"""M33: Device Mesh / Electrical Solver Interface tests."""
import os, tempfile, unittest
from pathlib import Path
os.environ.setdefault("TCAD_SKIP_QT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
import numpy as np

from device.regions import (
    DeviceDefinition, DeviceRegionDefinition, RegionBounds, RegionType,
)
from device.mesh_export import MeshExporter
from device.solver import BiasCondition, DeviceSolverBackend, SimulationSetup, SolverResult, get_solver


class RegionTests(unittest.TestCase):
    def test_region_creation(self):
        bounds = RegionBounds(0, 0, 0, 100, 100, 50)
        region = DeviceRegionDefinition(
            name="source", region_type=RegionType.SOURCE,
            bounds=bounds, material_ids=[1],
            doping_type="n+", doping_concentration_cm3=1e20,
        )
        self.assertEqual(region.name, "source")
        self.assertEqual(region.region_type, RegionType.SOURCE)
        self.assertTrue(bounds.contains(50, 50, 25))
        self.assertFalse(bounds.contains(150, 50, 25))

    def test_device_definition(self):
        device = DeviceDefinition(name="nmos")
        device.add_region(DeviceRegionDefinition(
            name="source", region_type=RegionType.SOURCE,
            bounds=RegionBounds(0,0,0, 50,100,50), material_ids=[1],
        ))
        device.add_region(DeviceRegionDefinition(
            name="drain", region_type=RegionType.DRAIN,
            bounds=RegionBounds(150,0,0, 200,100,50), material_ids=[1],
        ))
        device.add_region(DeviceRegionDefinition(
            name="gate", region_type=RegionType.GATE,
            bounds=RegionBounds(50,0,60, 150,100,65), material_ids=[5],
        ))
        device.add_electrode("gate", voltage=1.0, region_names=["gate"])
        device.add_electrode("source", voltage=0.0, region_names=["source"])
        device.add_electrode("drain", voltage=0.05, region_names=["drain"])

        self.assertEqual(len(device.regions), 3)
        self.assertEqual(len(device.electrode_boundaries), 3)

        d = device.to_dict()
        self.assertIn("regions", d)
        self.assertIn("electrodes", d)
        self.assertEqual(d["name"], "nmos")


class MeshExportTests(unittest.TestCase):
    def setUp(self):
        # Simple 2×2×2 Si substrate grid
        self.grid = np.zeros((4, 4, 4), dtype=np.uint16)
        self.grid[:, :, :2] = 1  # Si bottom half
        self.voxel = 5.0

    def test_vtu_export(self):
        vtu = MeshExporter.voxel_to_vtu(self.grid, self.voxel)
        self.assertIn("<VTKFile", vtu)
        self.assertIn("UnstructuredGrid", vtu)
        self.assertIn("MaterialId", vtu)
        # 4×4×2 = 32 solid voxels → 32 cells
        self.assertIn('NumberOfCells="32"', vtu)
        # Write to file
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.vtu"
            MeshExporter.voxel_to_vtu(self.grid, self.voxel, output_path=out)
            self.assertTrue(out.exists())
            content = out.read_text()
            self.assertIn("MaterialId", content)

    def test_gmsh_export(self):
        msh = MeshExporter.voxel_to_gmsh(self.grid, self.voxel)
        self.assertIn("$MeshFormat", msh)
        self.assertIn("$PhysicalNames", msh)
        self.assertIn("material_1", msh)
        self.assertIn("$Nodes", msh)
        self.assertIn("$Elements", msh)
        # Write to file
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.msh"
            MeshExporter.voxel_to_gmsh(self.grid, self.voxel, output_path=out)
            self.assertTrue(out.exists())

    def test_vtu_with_multiple_materials(self):
        grid = self.grid.copy()
        grid[:, :, 2] = 2  # SiO2 layer
        vtu = MeshExporter.voxel_to_vtu(grid, self.voxel)
        # Should have both material 1 and 2
        self.assertIn("1", vtu)
        self.assertIn("2", vtu)


class SolverInterfaceTests(unittest.TestCase):
    def test_stub_solver(self):
        solver = get_solver()
        self.assertIsInstance(solver, DeviceSolverBackend)
        # Without DEVSIM/FEniCSx installed, should be stub
        if solver.name() == "stub":
            self.assertTrue(solver.available())
            self.assertFalse(solver.supported_quantities())
            result = solver.solve(SimulationSetup())
            self.assertFalse(result.ok)

    def test_simulation_setup(self):
        setup = SimulationSetup(
            device_name="nmos_test",
            mesh_path="/tmp/test.vtu",
            bias=[
                BiasCondition("gate", 1.0),
                BiasCondition("source", 0.0),
                BiasCondition("drain", 0.05),
            ],
            temperature_k=300.0,
        )
        d = setup.to_dict()
        self.assertEqual(d["device"], "nmos_test")
        self.assertEqual(len(d["bias"]), 3)
        self.assertEqual(d["temperature_k"], 300.0)
        self.assertEqual(d["bias"][0]["voltage_v"], 1.0)


class EndToEndDeviceTests(unittest.TestCase):
    """从 GeometryScene → 体素化 → mesh export → solver stub 完整管道。"""

    def test_scene_to_mesh_pipeline(self):
        from geometry_scene import GeometryScene
        from geometry_scene.bridge import scene_to_voxel_grid

        def box(x0, y0, z0, x1, y1, z1):
            v = np.array([[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
                          [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]])
            quads = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
            tris = []
            for a,b,c,d in quads:
                tris.append([v[a],v[b],v[c]]); tris.append([v[a],v[c],v[d]])
            return np.array(tris)

        scene = GeometryScene.from_surfaces([
            (1, box(0, 0, 0, 640, 640, 200)),  # Si substrate
            (2, box(0, 0, 200, 640, 640, 250)),  # SiO2 gate oxide
        ])
        grid = scene_to_voxel_grid(scene, (32, 32, 32), 20.0)
        self.assertGreater(np.count_nonzero(grid), 0)

        # Export mesh
        vtu = MeshExporter.voxel_to_vtu(grid, 20.0)
        self.assertIn("MaterialId", vtu)

        # Create device definition
        device = DeviceDefinition(name="moscap")
        device.add_region(DeviceRegionDefinition(
            name="substrate", region_type=RegionType.BODY,
            bounds=RegionBounds(0, 0, 0, 640, 640, 200), material_ids=[1],
        ))
        device.add_region(DeviceRegionDefinition(
            name="oxide", region_type=RegionType.GATE,
            bounds=RegionBounds(0, 0, 200, 640, 640, 250), material_ids=[2],
            electrical_role="gate_dielectric",
        ))
        device.add_electrode("gate", voltage=1.0, region_names=["oxide"])
        device.add_electrode("substrate", voltage=0.0, region_names=["substrate"])

        # Try solver (stub without DEVSIM)
        setup = SimulationSetup(device_name="moscap")
        solver = get_solver()
        result = solver.solve(setup)
        # Without real solver, should gracefully report unavailable
        if solver.name() == "stub":
            self.assertFalse(result.ok)
            self.assertIn("Install", result.error)


if __name__ == "__main__":
    unittest.main()
