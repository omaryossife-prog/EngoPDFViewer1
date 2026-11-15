import pytest

fitz = pytest.importorskip("pymupdf")


def test_rich_freetext_bold_italic_survives_metadata_update_and_pdf_roundtrip(tmp_path):
    document = fitz.open()
    page = document.new_page(width=360, height=120)
    rich_html = (
        '<p style="font-family:Helvetica;font-size:16pt;color:#263247;'
        'text-align:left;margin:0"><b><i>Scanned by CamScanner</i></b></p>'
    )
    annotation = page.add_freetext_annot(
        fitz.Rect(20, 20, 330, 92),
        rich_html,
        fontsize=16,
        fontname="Helv",
        text_color=(0.15, 0.20, 0.28),
        fill_color=(1.0, 0.96, 0.76),
        richtext=True,
    )
    annotation.update()
    xref = int(annotation.xref)

    # Contents / title are set at the xref level after rich-text creation.
    # Calling Annot.set_info() here would replace /RC and discard <b>/<i>.
    document.xref_set_key(xref, "Contents", fitz.get_pdf_str("Scanned by CamScanner"))
    document.xref_set_key(xref, "T", fitz.get_pdf_str("Engo PDF Text"))
    output = tmp_path / "rich-text-roundtrip.pdf"
    document.save(output)
    document.close()

    reopened = fitz.open(output)
    rich = reopened.xref_get_key(xref, "RC")[1]
    assert "<b>" in rich
    assert "<i>" in rich
    assert "font-size:16pt" in rich
    reopened.close()


def test_multiply_highlighter_keeps_black_pdf_ink_black(tmp_path):
    document = fitz.open()
    page = document.new_page(width=300, height=100)
    page.insert_text(
        (20, 60), "Scanned by CamScanner",
        fontsize=22, color=(0, 0, 0),
    )
    marker = page.add_ink_annot([[(15, 42), (278, 42)]])
    marker.set_colors(stroke=(245 / 255, 211 / 255, 78 / 255))
    marker.set_border(width=12)
    marker.set_opacity(0.72)
    marker.set_blendmode("Multiply")
    marker.update()

    output = tmp_path / "multiply-highlighter.pdf"
    document.save(output)
    document.close()

    reopened = fitz.open(output)
    pixmap = reopened[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    # This location lies on the black glyph; another lies on the marker alone.
    assert max(pixmap.pixel(50, 88)) < 10
    marker_only = pixmap.pixel(250, 90)
    assert marker_only[0] > marker_only[1] > marker_only[2]
    reopened.close()
