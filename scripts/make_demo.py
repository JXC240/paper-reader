"""Generate an original PDF fixture. Requires reportlab only for regeneration."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth

ROOT = Path(__file__).resolve().parents[1]


def paragraph(c, text, x, top, width=235, size=11):
    c.setFont("Times-Roman", size)
    words, line, y = text.split(), "", top
    for word in words:
        proposed = (line + " " + word).strip()
        if stringWidth(proposed, "Times-Roman", size) > width:
            c.drawString(x, y, line)
            y -= 17
            line = word
        else:
            line = proposed
    if line:
        c.drawString(x, y, line)
    return y - 28


def main():
    target = ROOT / "examples" / "reader-demo.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(target), pagesize=(612, 792), invariant=1)
    c.setTitle("Paper Reader - Original Reading Demo")
    c.setAuthor("Paper Reader contributors")
    c.setFillColor(HexColor("#24665b"))
    c.setFont("Helvetica", 10)
    c.drawString(48, 747, "PAPER READER / ORIGINAL TEST DOCUMENT")
    c.setFillColor(HexColor("#243a36"))
    c.setFont("Times-Roman", 25)
    c.drawString(48, 705, "A small page for a careful reader.")
    c.setFont("Helvetica", 10)
    c.drawString(48, 679, "Select a sentence. Keep its place. Return to the conversation.")
    c.setStrokeColor(HexColor("#d5dfd3"))
    c.line(48, 657, 564, 657)
    left = [
        "A highlight is a question waiting to be understood. It does not mean that the reader has already learned the sentence.",
        "Reading slowly can reveal how a sentence is built. A small word may change the relationship between two ideas, even when every individual word looks familiar.",
        "The original sentence should remain available together with its page number. Context helps a reader decide which meaning fits the passage.",
        "This page uses two columns so that selection order and saved coordinates can be tested. The paragraphs are original demonstration text, not scientific evidence."
    ]
    right = [
        "A saved annotation should survive a closed window. When the document is opened again, the same passage should still be highlighted.",
        "Changing the zoom level changes the size of the page on screen. It should not change the location of a highlight inside the document.",
        "A note can contain a translation, a question, or an explanation. A vocabulary entry is different: the reader explicitly chooses to collect a word.",
        "When sharing the tool, use this original example instead of a private paper. A useful prototype should be easy to start and possible to test."
    ]
    for x, texts in [(48, left), (326, right)]:
        y = 625
        for text in texts:
            y = paragraph(c, text, x, y)
    c.setFont("Helvetica", 9)
    c.drawString(48, 34, "Original demo text - no scientific claims or research results")
    c.drawRightString(564, 34, "1")
    c.showPage()
    c.setFillColor(HexColor("#243a36"))
    c.setFont("Times-Roman", 25)
    c.drawString(48, 724, "Keep the context, not just the word.")
    paragraph(c, "A single word can be highlighted while the rest of its sentence stays nearby. The reading record should preserve both the selected word and the surrounding original text.", 48, 675, 510, 13)
    paragraph(c, "Try highlighting the word surrounding in the sentence above. Then mark it as vocabulary, add a short note, export the Markdown file, and reopen the PDF.", 48, 565, 510, 13)
    paragraph(c, "All numbers and statements in this document are examples for software testing. This document contains no extracted paper content.", 48, 465, 510, 13)
    c.setFont("Helvetica", 9)
    c.drawString(48, 34, "Original demo text - a second page for persistence tests")
    c.drawRightString(564, 34, "2")
    c.save()
    print(target)


if __name__ == "__main__":
    main()
