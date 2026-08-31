def test_streamlit_module_importable():
    import sre_agent.channels.streamlit_app as m

    assert hasattr(m, "main")
