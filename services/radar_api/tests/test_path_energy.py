import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
SIONNA_SRC = REPO_ROOT / "experiments" / "sionna_radar" / "src"
if str(SIONNA_SRC) not in sys.path:
    sys.path.insert(0, str(SIONNA_SRC))

from sionna_radar.processing import PathArrays, canonicalize_path_arrays, path_energy_from_cir


def test_path_energy_from_legacy_c002_cir_shape() -> None:
    a = np.zeros((1, 2, 1, 1, 3, 1), dtype=np.complex64)
    a[0, :, 0, 0, 0, 0] = [1 + 0j, 2 + 0j]
    a[0, :, 0, 0, 1, 0] = [0 + 1j, 0 + 2j]
    a[0, :, 0, 0, 2, 0] = [3 + 0j, 4 + 0j]

    energy = path_energy_from_cir(a, path_count=3)

    np.testing.assert_allclose(energy, [5.0, 5.0, 25.0])


def test_path_energy_from_worker_cir_shape() -> None:
    a = np.zeros((1, 1, 2, 1, 1, 3, 1), dtype=np.complex64)
    a[0, 0, :, 0, 0, 0, 0] = [1 + 0j, 2 + 0j]
    a[0, 0, :, 0, 0, 1, 0] = [0 + 1j, 0 + 2j]
    a[0, 0, :, 0, 0, 2, 0] = [3 + 0j, 4 + 0j]

    energy = path_energy_from_cir(a, path_count=3)

    np.testing.assert_allclose(energy, [5.0, 5.0, 25.0])


def test_canonicalize_real_array_path_metadata_preserves_per_path_alignment() -> None:
    path_count = 3
    link_shape = (1, 2, 1, 1, path_count)
    tau = np.asarray(
        [[[[[1.0e-6, -1.0, 3.0e-6]]], [[[1.1e-6, 2.0e-6, 3.1e-6]]]]],
        dtype=np.float32,
    )
    valid = tau > 0.0
    phi = np.arange(np.prod(link_shape), dtype=np.float32).reshape(link_shape)
    interactions = np.zeros((1, *link_shape), dtype=np.uint32)
    interactions[0, 0, 0, 0, 0, 0] = 1
    interactions[0, 0, 1, 0, 0, 1] = 2
    objects = interactions.copy()
    vertices = np.zeros((1, *link_shape, 3), dtype=np.float32)
    vertices[0, 0, 1, 0, 0, 1] = [2.0, 3.0, 4.0]
    arrays = PathArrays(
        tau_s=tau,
        valid=valid,
        theta_r_rad=phi,
        phi_r_rad=phi,
        theta_t_rad=phi,
        phi_t_rad=phi,
        doppler_hz=phi,
        interactions=interactions,
        objects=objects,
        vertices=vertices,
        a_cir=np.zeros((*link_shape, 1), dtype=np.complex64),
        tau_cir_s=tau,
    )

    canonical, changed = canonicalize_path_arrays(arrays)

    assert changed is True
    assert canonical.tau_s.shape == (1, 1, path_count)
    np.testing.assert_allclose(canonical.tau_s.reshape(-1), [1.0e-6, 2.0e-6, 3.0e-6])
    np.testing.assert_array_equal(canonical.valid.reshape(-1), [True, True, True])
    np.testing.assert_array_equal(canonical.interactions.reshape(1, path_count), [[1, 2, 0]])
    np.testing.assert_allclose(canonical.vertices.reshape(1, path_count, 3)[0, 1], [2.0, 3.0, 4.0])
