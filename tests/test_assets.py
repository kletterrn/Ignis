from services import assets


def test_shared_assets_change_url_only_when_content_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, 'STATIC', tmp_path)
    style = tmp_path / 'styles.css'
    style.write_text('body{margin:0}')
    before = assets.asset_url('styles.css')
    assert before == assets.asset_url('styles.css')
    assert assets.asset_url('styles.css', './static/') == '.' + before
    style.write_text('body{margin:1px}')
    assert assets.asset_url('styles.css') != before
