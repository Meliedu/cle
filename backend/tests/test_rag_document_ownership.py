import pytest


@pytest.mark.skip(reason="Requires seeded cross-course fixtures; enable when available")
def test_cross_course_document_ids_rejected():
    pass


def test_rag_module_imports_cleanly():
    import app.api.rag as rag_module
    assert hasattr(rag_module, "router")
