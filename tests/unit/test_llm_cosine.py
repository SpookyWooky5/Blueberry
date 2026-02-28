import numpy as np
import pytest
from LLM.cosine import cosine


def test_identical_vectors_score_one():
    a = np.array([1.0, 0.0, 0.0])
    assert cosine(a, a) == pytest.approx(1.0)


def test_orthogonal_vectors_score_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine(a, b) == pytest.approx(0.0)


def test_zero_vector_a_returns_zero():
    a = np.array([0.0, 0.0])
    b = np.array([1.0, 2.0])
    assert cosine(a, b) == 0


def test_zero_vector_b_returns_zero():
    a = np.array([1.0, 2.0])
    b = np.array([0.0, 0.0])
    assert cosine(a, b) == 0


def test_antiparallel_vectors_score_minus_one():
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    assert cosine(a, b) == pytest.approx(-1.0)


def test_general_vectors():
    a = np.array([3.0, 4.0])
    b = np.array([4.0, 3.0])
    result = cosine(a, b)
    assert 0.9 < result < 1.0


def test_both_zero_vectors_returns_zero():
    a = np.array([0.0, 0.0])
    assert cosine(a, a) == 0
