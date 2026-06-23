def test_vocab_loads_from_template(vocab):
    assert len(vocab["manufacturers"]) > 100
    assert "CommScope" in vocab["manufacturers"]
    assert "panel" in vocab["type"]
    assert "Custom" in vocab["frequency"]
    assert "750 MHz" in vocab["frequency"]
    assert "EMSS" in vocab["source"]
