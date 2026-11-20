using System.IO.Compression;
using System.Net;
using System.Text;
using System.Xml;
using System.Xml.Linq;
using Engo.Application.Documents;
using Engo.Domain.Documents;

namespace Engo.Infrastructure.Office;

/// <summary>
/// Read-only preview adapter for the common DOCX and PPTX Open XML packages.
/// It never writes back to the source document.
/// </summary>
public sealed class OpenXmlOfficeDocumentReader : IOfficeDocumentReader
{
    private const long MaximumPackageBytes = 256L * 1024 * 1024;
    private const long MaximumXmlCharacters = 32L * 1024 * 1024;
    private const long MaximumImageBytes = 32L * 1024 * 1024;
    private const int MaximumPackageEntries = 10_000;

    private static readonly XNamespace Word =
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    private static readonly XNamespace Drawing =
        "http://schemas.openxmlformats.org/drawingml/2006/main";
    private static readonly XNamespace Presentation =
        "http://schemas.openxmlformats.org/presentationml/2006/main";
    private static readonly XNamespace Relationships =
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private static readonly XNamespace PackageRelationships =
        "http://schemas.openxmlformats.org/package/2006/relationships";

    public Task<OfficeDocumentPreview> CreatePreviewAsync(
        string filePath,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(filePath);
        cancellationToken.ThrowIfCancellationRequested();

        return Task.Run(
            () => CreatePreview(filePath, cancellationToken),
            cancellationToken);
    }

    private static OfficeDocumentPreview CreatePreview(
        string filePath,
        CancellationToken cancellationToken)
    {
        var fullPath = Path.GetFullPath(filePath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("The Office document no longer exists.", fullPath);
        }

        var kind = Path.GetExtension(fullPath).ToLowerInvariant() switch
        {
            ".docx" => DocumentKind.Word,
            ".pptx" => DocumentKind.PowerPoint,
            _ => throw new NotSupportedException(
                "Only modern Word (.docx) and PowerPoint (.pptx) files are supported.")
        };

        var previewRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Engo",
            "Engo.WinUI",
            "OfficePreviews");
        if (string.IsNullOrWhiteSpace(Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData)))
        {
            previewRoot = Path.Combine(Path.GetTempPath(), "Engo", "OfficePreviews");
        }

        Directory.CreateDirectory(previewRoot);
        var previewDirectory = Path.Combine(previewRoot, Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(previewDirectory);
        Directory.CreateDirectory(Path.Combine(previewDirectory, "media"));

        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            using var archive = ZipFile.OpenRead(fullPath);
            ValidatePackage(archive);

            var pages = kind == DocumentKind.Word
                ? ReadWordDocument(archive, fullPath, previewDirectory, cancellationToken)
                : ReadPowerPointDocument(archive, fullPath, previewDirectory, cancellationToken);

            if (pages.Count == 0)
            {
                throw new InvalidDataException("The Office document does not contain readable content.");
            }

            cancellationToken.ThrowIfCancellationRequested();
            return new OfficeDocumentPreview(
                fullPath,
                kind,
                previewDirectory,
                pages);
        }
        catch
        {
            TryDeleteDirectory(previewDirectory);
            throw;
        }
    }

    private static void ValidatePackage(ZipArchive archive)
    {
        if (archive.Entries.Count == 0 || archive.Entries.Count > MaximumPackageEntries)
        {
            throw new InvalidDataException("The Office package contains an invalid number of entries.");
        }

        long totalUncompressedBytes = 0;
        foreach (var entry in archive.Entries)
        {
            totalUncompressedBytes = checked(totalUncompressedBytes + entry.Length);
            if (totalUncompressedBytes > MaximumPackageBytes)
            {
                throw new InvalidDataException(
                    "The Office document is too large to preview safely (maximum 256 MB unpacked).");
            }
        }
    }

    private static List<OfficeDocumentPage> ReadWordDocument(
        ZipArchive archive,
        string sourcePath,
        string previewDirectory,
        CancellationToken cancellationToken)
    {
        var document = LoadXml(archive, "word/document.xml");
        var body = document.Root?.Element(Word + "body")
            ?? throw new InvalidDataException("The Word document body is missing.");
        var relationships = ReadRelationships(archive, "word/document.xml");
        var imageCache = new Dictionary<string, string>(StringComparer.Ordinal);

        var content = new StringBuilder();
        foreach (var block in body.Elements())
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (block.Name == Word + "p")
            {
                content.Append(RenderWordParagraph(
                    block, archive, relationships, imageCache, previewDirectory));
            }
            else if (block.Name == Word + "tbl")
            {
                content.Append(RenderWordTable(
                    block, archive, relationships, imageCache, previewDirectory));
            }
        }

        if (content.Length == 0)
        {
            content.Append("<p class=\"empty\">This Word document contains no readable paragraphs or tables.</p>");
        }

        var html = BuildHtml(
            Path.GetFileName(sourcePath),
            "word-document",
            content.ToString());
        var htmlPath = Path.Combine(previewDirectory, "document.html");
        File.WriteAllText(htmlPath, html, new UTF8Encoding(false));

        return
        [
            new OfficeDocumentPage("مستند Word", htmlPath)
        ];
    }

    private static string RenderWordParagraph(
        XElement paragraph,
        ZipArchive archive,
        IReadOnlyDictionary<string, RelationshipTarget> relationships,
        IDictionary<string, string> imageCache,
        string previewDirectory)
    {
        var styleName = (string?)paragraph
            .Element(Word + "pPr")?
            .Element(Word + "pStyle")?
            .Attribute(Word + "val") ?? string.Empty;

        var tag = GetWordParagraphTag(styleName);
        var alignment = (string?)paragraph
            .Element(Word + "pPr")?
            .Element(Word + "jc")?
            .Attribute(Word + "val");
        var isRightToLeft = paragraph.Descendants(Word + "rtl").Any() ||
                            paragraph.Element(Word + "pPr")?.Element(Word + "bidi") is not null ||
                            paragraph.Descendants(Word + "t").Any(node => ContainsArabic(node.Value));
        var style = BuildAlignmentStyle(alignment);
        if (isRightToLeft)
        {
            if (string.IsNullOrWhiteSpace(style))
            {
                style = "text-align:right";
            }

            style += ";direction:rtl;unicode-bidi:plaintext";
        }

        var inner = new StringBuilder();
        foreach (var child in paragraph.Elements())
        {
            if (child.Name == Word + "r")
            {
                inner.Append(RenderWordRun(
                    child, archive, relationships, imageCache, previewDirectory));
            }
            else if (child.Name == Word + "hyperlink")
            {
                foreach (var run in child.Elements(Word + "r"))
                {
                    inner.Append(RenderWordRun(
                        run, archive, relationships, imageCache, previewDirectory));
                }
            }
        }

        if (inner.Length == 0)
        {
            return string.Empty;
        }

        var styleAttribute = string.IsNullOrWhiteSpace(style)
            ? string.Empty
            : $" style=\"{WebUtility.HtmlEncode(style)}\"";
        return $"<{tag}{styleAttribute}>{inner}</{tag}>";
    }

    private static string RenderWordRun(
        XElement run,
        ZipArchive archive,
        IReadOnlyDictionary<string, RelationshipTarget> relationships,
        IDictionary<string, string> imageCache,
        string previewDirectory)
    {
        var properties = run.Element(Word + "rPr");
        var styles = new List<string>();

        if (properties?.Element(Word + "b") is not null)
        {
            styles.Add("font-weight:700");
        }

        if (properties?.Element(Word + "i") is not null)
        {
            styles.Add("font-style:italic");
        }

        if (properties?.Element(Word + "u") is not null)
        {
            styles.Add("text-decoration:underline");
        }

        var color = NormalizeHexColor((string?)properties?.Element(Word + "color")?.Attribute(Word + "val"));
        if (color is not null)
        {
            styles.Add($"color:#{color}");
        }

        var size = ParsePositiveNumber((string?)properties?.Element(Word + "sz")?.Attribute(Word + "val"));
        if (size.HasValue)
        {
            styles.Add($"font-size:{Math.Clamp(size.Value / 2, 6, 48):0.##}pt");
        }

        var highlight = (string?)properties?.Element(Word + "highlight")?.Attribute(Word + "val");
        var highlightColor = GetHighlightColor(highlight);
        if (highlightColor is not null)
        {
            styles.Add($"background-color:#{highlightColor}");
        }

        var content = new StringBuilder();
        foreach (var node in run.Elements())
        {
            if (node.Name == Word + "rPr")
            {
                continue;
            }

            if (node.Name == Word + "t")
            {
                content.Append(WebUtility.HtmlEncode(node.Value));
            }
            else if (node.Name == Word + "tab")
            {
                content.Append("&emsp;");
            }
            else if (node.Name == Word + "br" || node.Name == Word + "cr")
            {
                content.Append("<br>");
            }
            else if (node.Name == Word + "drawing" || node.Name == Word + "pict")
            {
                foreach (var blip in node.Descendants(Drawing + "blip"))
                {
                    var relationshipId = (string?)blip.Attribute(Relationships + "embed");
                    var imageSource = MaterializeImage(
                        archive,
                        "word/document.xml",
                        relationships,
                        relationshipId,
                        imageCache,
                        previewDirectory);
                    if (imageSource is not null)
                    {
                        content.Append(
                            $"<img class=\"word-image\" src=\"{WebUtility.HtmlEncode(imageSource)}\" alt=\"Embedded image\">");
                    }
                }
            }
        }

        if (styles.Count == 0)
        {
            return content.ToString();
        }

        return $"<span style=\"{WebUtility.HtmlEncode(string.Join(";", styles))}\">{content}</span>";
    }

    private static string RenderWordTable(
        XElement table,
        ZipArchive archive,
        IReadOnlyDictionary<string, RelationshipTarget> relationships,
        IDictionary<string, string> imageCache,
        string previewDirectory)
    {
        var rows = table.Elements(Word + "tr").ToArray();
        if (rows.Length == 0)
        {
            return string.Empty;
        }

        var html = new StringBuilder("<table><tbody>");
        for (var rowIndex = 0; rowIndex < rows.Length; rowIndex++)
        {
            html.Append("<tr>");
            foreach (var cell in rows[rowIndex].Elements(Word + "tc"))
            {
                var paragraphs = cell.Elements(Word + "p")
                    .Select(p => RenderWordParagraph(
                        p, archive, relationships, imageCache, previewDirectory))
                    .Where(value => !string.IsNullOrWhiteSpace(value));
                var tag = rowIndex == 0 ? "th" : "td";
                html.Append('<').Append(tag).Append('>')
                    .Append(string.Join(string.Empty, paragraphs))
                    .Append("</").Append(tag).Append('>');
            }

            html.Append("</tr>");
        }

        html.Append("</tbody></table>");
        return html.ToString();
    }

    private static List<OfficeDocumentPage> ReadPowerPointDocument(
        ZipArchive archive,
        string sourcePath,
        string previewDirectory,
        CancellationToken cancellationToken)
    {
        var presentation = LoadXml(archive, "ppt/presentation.xml");
        var slideList = presentation.Root?
            .Element(Presentation + "sldIdLst")?
            .Elements(Presentation + "sldId")
            .ToArray() ?? [];

        if (slideList.Length == 0)
        {
            throw new InvalidDataException("The PowerPoint presentation does not contain any slides.");
        }

        var presentationRelationships = ReadRelationships(archive, "ppt/presentation.xml");
        var slideSize = presentation.Root?.Element(Presentation + "sldSz");
        var slideWidth = ParsePositiveNumber((string?)slideSize?.Attribute("cx")) ?? 12_192_000;
        var slideHeight = ParsePositiveNumber((string?)slideSize?.Attribute("cy")) ?? 6_858_000;
        var imageCache = new Dictionary<string, string>(StringComparer.Ordinal);
        var pages = new List<OfficeDocumentPage>(slideList.Length);
        var slideDirectory = Path.Combine(previewDirectory, "slides");
        Directory.CreateDirectory(slideDirectory);

        for (var index = 0; index < slideList.Length; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var relationshipId = (string?)slideList[index].Attribute(Relationships + "id");
            if (relationshipId is null ||
                !presentationRelationships.TryGetValue(relationshipId, out var relationship))
            {
                throw new InvalidDataException($"PowerPoint slide {index + 1} has a missing relationship.");
            }

            var slidePart = ResolvePackageTarget("ppt/presentation.xml", relationship.Target);
            var slideXml = LoadXml(archive, slidePart);
            var slideRelationships = ReadRelationships(archive, slidePart);
            var htmlContent = RenderPowerPointSlide(
                slideXml,
                archive,
                slidePart,
                slideRelationships,
                imageCache,
                previewDirectory,
                slideWidth,
                slideHeight);

            var html = BuildHtml(
                $"{Path.GetFileName(sourcePath)} · Slide {index + 1}",
                "powerpoint-slide",
                htmlContent);
            var htmlPath = Path.Combine(slideDirectory, $"slide-{index + 1:0000}.html");
            File.WriteAllText(htmlPath, html, new UTF8Encoding(false));

            pages.Add(new OfficeDocumentPage(
                $"الشريحة {index + 1} / {slideList.Length}",
                htmlPath));
        }

        return pages;
    }

    private static string RenderPowerPointSlide(
        XDocument slideDocument,
        ZipArchive archive,
        string slidePart,
        IReadOnlyDictionary<string, RelationshipTarget> relationships,
        IDictionary<string, string> imageCache,
        string previewDirectory,
        double slideWidth,
        double slideHeight)
    {
        var slide = slideDocument.Root;
        var backgroundColorNode = slide?.Descendants(Presentation + "bg")
            .SelectMany(background => background.Descendants(Drawing + "srgbClr"))
            .FirstOrDefault();
        var backgroundColor = NormalizeHexColor(
            (string?)backgroundColorNode?.Attribute("val")) ?? "FFFFFF";

        var shapeTree = slide?.Descendants(Presentation + "spTree").FirstOrDefault();
        var elements = new StringBuilder();
        if (shapeTree is not null)
        {
            foreach (var shape in shapeTree.Elements())
            {
                if (shape.Name == Presentation + "sp")
                {
                    var text = RenderPowerPointTextShape(shape);
                    if (text.Length > 0)
                    {
                        elements.Append(WrapPositionedShape(
                            shape, slideWidth, slideHeight, text));
                    }
                }
                else if (shape.Name == Presentation + "pic")
                {
                    var blip = shape.Descendants(Drawing + "blip").FirstOrDefault();
                    var relationshipId = (string?)blip?.Attribute(Relationships + "embed");
                    var imageSource = MaterializeImage(
                        archive,
                        slidePart,
                        relationships,
                        relationshipId,
                        imageCache,
                        previewDirectory);
                    if (imageSource is not null)
                    {
                        var image = $"<img class=\"slide-image\" src=\"{WebUtility.HtmlEncode(imageSource)}\" alt=\"Slide image\">";
                        elements.Append(WrapPositionedShape(
                            shape, slideWidth, slideHeight, image));
                    }
                }
                else if (shape.Name == Presentation + "graphicFrame")
                {
                    var table = shape.Descendants(Drawing + "tbl").FirstOrDefault();
                    if (table is not null)
                    {
                        elements.Append(WrapPositionedShape(
                            shape,
                            slideWidth,
                            slideHeight,
                            RenderPowerPointTable(table)));
                    }
                }
            }
        }

        return $"""
            <div class="slide-stage" style="aspect-ratio:{slideWidth:0.##}/{slideHeight:0.##};background:#{backgroundColor}">
              {elements}
            </div>
            """;
    }

    private static string RenderPowerPointTextShape(XElement shape)
    {
        var textBody = shape.Element(Presentation + "txBody");
        if (textBody is null)
        {
            return string.Empty;
        }

        var paragraphs = new StringBuilder();
        foreach (var paragraph in textBody.Elements(Drawing + "p"))
        {
            var paragraphProperties = paragraph.Element(Drawing + "pPr");
            var alignment = (string?)paragraphProperties?.Attribute("algn");
            var isRightToLeft =
                (string?)paragraphProperties?.Attribute("rtl") == "1" ||
                paragraph.Descendants(Drawing + "t").Any(node => ContainsArabic(node.Value));
            var style = BuildAlignmentStyle(alignment);
            if (isRightToLeft)
            {
                if (string.IsNullOrWhiteSpace(style))
                {
                    style = "text-align:right";
                }

                style += ";direction:rtl;unicode-bidi:plaintext";
            }

            var runs = new StringBuilder();

            foreach (var node in paragraph.Elements())
            {
                if (node.Name == Drawing + "r")
                {
                    var runProperties = node.Element(Drawing + "rPr");
                    var runStyle = new List<string>();
                    if ((string?)runProperties?.Attribute("b") == "1")
                    {
                        runStyle.Add("font-weight:700");
                    }

                    if ((string?)runProperties?.Attribute("i") == "1")
                    {
                        runStyle.Add("font-style:italic");
                    }

                    if ((string?)runProperties?.Attribute("u") is not null and not "none")
                    {
                        runStyle.Add("text-decoration:underline");
                    }

                    var color = NormalizeHexColor(
                        (string?)runProperties?.Element(Drawing + "solidFill")?
                            .Element(Drawing + "srgbClr")?.Attribute("val"));
                    if (color is not null)
                    {
                        runStyle.Add($"color:#{color}");
                    }

                    var fontSize = ParsePositiveNumber((string?)runProperties?.Attribute("sz"));
                    if (fontSize.HasValue)
                    {
                        runStyle.Add($"font-size:{Math.Clamp(fontSize.Value / 100, 6, 54):0.##}pt");
                    }

                    var value = WebUtility.HtmlEncode(
                        (string?)node.Element(Drawing + "t") ?? string.Empty);
                    runs.Append(runStyle.Count == 0
                        ? value
                        : $"<span style=\"{WebUtility.HtmlEncode(string.Join(";", runStyle))}\">{value}</span>");
                }
                else if (node.Name == Drawing + "br")
                {
                    runs.Append("<br>");
                }
                else if (node.Name == Drawing + "fld")
                {
                    runs.Append(WebUtility.HtmlEncode(
                        (string?)node.Element(Drawing + "t") ?? string.Empty));
                }
            }

            if (runs.Length > 0)
            {
                var styleAttribute = string.IsNullOrWhiteSpace(style)
                    ? string.Empty
                    : $" style=\"{WebUtility.HtmlEncode(style)}\"";
                paragraphs.Append($"<p{styleAttribute}>{runs}</p>");
            }
        }

        return paragraphs.ToString();
    }

    private static string RenderPowerPointTable(XElement table)
    {
        var html = new StringBuilder("<table><tbody>");
        var rows = table.Elements(Drawing + "tr").ToArray();
        for (var rowIndex = 0; rowIndex < rows.Length; rowIndex++)
        {
            html.Append("<tr>");
            foreach (var cell in rows[rowIndex].Elements(Drawing + "tc"))
            {
                var text = cell.Descendants(Drawing + "t")
                    .Select(node => WebUtility.HtmlEncode(node.Value));
                var tag = rowIndex == 0 ? "th" : "td";
                html.Append('<').Append(tag).Append('>')
                    .Append(string.Join("<br>", text))
                    .Append("</").Append(tag).Append('>');
            }

            html.Append("</tr>");
        }

        html.Append("</tbody></table>");
        return html.ToString();
    }

    private static string WrapPositionedShape(
        XElement shape,
        double slideWidth,
        double slideHeight,
        string content)
    {
        var transform = shape.Element(Presentation + "spPr")?.Element(Drawing + "xfrm")
            ?? shape.Element(Presentation + "xfrm")
            ?? shape.Descendants(Drawing + "xfrm").FirstOrDefault();
        var offset = transform?.Element(Drawing + "off");
        var extent = transform?.Element(Drawing + "ext");
        if (offset is null || extent is null)
        {
            return $"<div class=\"slide-shape\">{content}</div>";
        }

        var x = ParsePositiveOrSignedNumber((string?)offset.Attribute("x")) ?? 0;
        var y = ParsePositiveOrSignedNumber((string?)offset.Attribute("y")) ?? 0;
        var width = ParsePositiveNumber((string?)extent.Attribute("cx")) ?? 0;
        var height = ParsePositiveNumber((string?)extent.Attribute("cy")) ?? 0;
        if (width <= 0 || height <= 0)
        {
            return $"<div class=\"slide-shape\">{content}</div>";
        }

        var left = Math.Clamp(x / slideWidth * 100, 0, 99.5);
        var top = Math.Clamp(y / slideHeight * 100, 0, 99.5);
        var widthPercent = Math.Clamp(width / slideWidth * 100, 0.5, 100 - left);
        var heightPercent = Math.Clamp(height / slideHeight * 100, 0.5, 100 - top);

        return $"""
            <div class="slide-shape" style="left:{left:0.###}%;top:{top:0.###}%;width:{widthPercent:0.###}%;height:{heightPercent:0.###}%">
              {content}
            </div>
            """;
    }

    private static string BuildHtml(string title, string bodyClass, string body)
    {
        var safeTitle = WebUtility.HtmlEncode(title);
        return $$"""
            <!doctype html>
            <html lang="ar">
            <head>
              <meta charset="utf-8">
              <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline';">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>{{safeTitle}}</title>
              <style>
                * { box-sizing: border-box; }
                html, body { margin: 0; padding: 0; background: #f1f3f6; color: #202936; font-family: "Segoe UI", Arial, sans-serif; }
                body { padding: 24px; line-height: 1.6; }
                .document-title { color: #64748b; font-size: 12px; margin: 0 auto 18px; max-width: 1100px; border-bottom: 1px solid #d8dee8; padding-bottom: 10px; overflow-wrap: anywhere; }
                .word-document { max-width: 1000px; min-height: 800px; padding: 48px 56px; margin: 0 auto; background: white; box-shadow: 0 2px 12px #18223018; overflow-wrap: anywhere; }
                .word-document p { margin: 0 0 12px; white-space: pre-wrap; }
                .word-document h1, .word-document h2, .word-document h3, .word-document h4, .word-document h5, .word-document h6 { color: #243c5a; margin: 22px 0 10px; line-height: 1.3; }
                .word-document h1 { font-size: 28px; }
                .word-document h2 { font-size: 24px; }
                .word-document h3 { font-size: 21px; }
                table { width: 100%; border-collapse: collapse; margin: 14px 0 22px; }
                td, th { border: 1px solid #aeb8c5; padding: 7px 9px; vertical-align: top; text-align: start; }
                th { background: #eaf0f7; font-weight: 700; }
                img { max-width: 100%; height: auto; }
                .word-image { display: block; max-width: min(100%, 720px); margin: 10px auto; }
                .powerpoint-slide { padding: 8px; }
                .slide-stage { position: relative; overflow: hidden; width: min(100%, 1280px); margin: 0 auto; background: white; box-shadow: 0 2px 16px #18223025; }
                .slide-shape { position: absolute; overflow: hidden; padding: 3px; font-size: clamp(10px, 1.4vw, 24px); line-height: 1.25; overflow-wrap: anywhere; }
                .slide-shape p { margin: 0 0 4px; }
                .slide-image { display: block; width: 100%; height: 100%; object-fit: contain; }
                .empty { color: #64748b; font-style: italic; }
                @media (max-width: 700px) {
                  body { padding: 10px; }
                  .word-document { padding: 22px; }
                }
              </style>
            </head>
            <body>
              <div class="document-title">{{safeTitle}}</div>
              <main class="{{bodyClass}}">{{body}}</main>
            </body>
            </html>
            """;
    }

    private static Dictionary<string, RelationshipTarget> ReadRelationships(
        ZipArchive archive,
        string sourcePart)
    {
        var slash = sourcePart.LastIndexOf('/');
        var directory = slash < 0 ? string.Empty : sourcePart[..slash];
        var fileName = slash < 0 ? sourcePart : sourcePart[(slash + 1)..];
        var relationshipPath = string.IsNullOrEmpty(directory)
            ? $"_rels/{fileName}.rels"
            : $"{directory}/_rels/{fileName}.rels";
        var entry = archive.GetEntry(relationshipPath);
        if (entry is null)
        {
            return new Dictionary<string, RelationshipTarget>(StringComparer.Ordinal);
        }

        var xml = LoadXml(entry);
        var result = new Dictionary<string, RelationshipTarget>(StringComparer.Ordinal);
        foreach (var relationship in xml.Root?.Elements(PackageRelationships + "Relationship") ?? [])
        {
            var id = (string?)relationship.Attribute("Id");
            var target = (string?)relationship.Attribute("Target");
            var targetMode = (string?)relationship.Attribute("TargetMode");
            if (!string.IsNullOrWhiteSpace(id) &&
                !string.IsNullOrWhiteSpace(target) &&
                !string.Equals(targetMode, "External", StringComparison.OrdinalIgnoreCase))
            {
                result[id] = new RelationshipTarget(target);
            }
        }

        return result;
    }

    private static string? MaterializeImage(
        ZipArchive archive,
        string sourcePart,
        IReadOnlyDictionary<string, RelationshipTarget> relationships,
        string? relationshipId,
        IDictionary<string, string> imageCache,
        string previewDirectory)
    {
        if (string.IsNullOrWhiteSpace(relationshipId) ||
            !relationships.TryGetValue(relationshipId, out var relationship))
        {
            return null;
        }

        var packagePath = ResolvePackageTarget(sourcePart, relationship.Target);
        if (imageCache.TryGetValue(packagePath, out var cached))
        {
            return cached;
        }

        var entry = archive.GetEntry(packagePath);
        if (entry is null || entry.Length <= 0 || entry.Length > MaximumImageBytes)
        {
            return null;
        }

        var extension = Path.GetExtension(packagePath).ToLowerInvariant();
        if (extension is not (".png" or ".jpg" or ".jpeg" or ".gif" or ".bmp" or ".webp" or ".tif" or ".tiff"))
        {
            return null;
        }

        var mediaDirectory = Path.Combine(previewDirectory, "media");
        Directory.CreateDirectory(mediaDirectory);
        var outputName = $"media-{imageCache.Count + 1:0000}{extension}";
        var outputPath = Path.Combine(mediaDirectory, outputName);
        using (var source = entry.Open())
        using (var destination = new FileStream(
            outputPath,
            FileMode.CreateNew,
            FileAccess.Write,
            FileShare.None))
        {
            source.CopyTo(destination);
        }

        var relativePath = $"media/{outputName}";
        imageCache[packagePath] = relativePath;
        return relativePath;
    }

    private static string ResolvePackageTarget(string sourcePart, string target)
    {
        var normalizedTarget = target.Replace('\\', '/');
        var segments = normalizedTarget.StartsWith('/')
            ? new List<string>()
            : sourcePart.Split('/').SkipLast(1).ToList();

        foreach (var segment in normalizedTarget.Split('/'))
        {
            if (string.IsNullOrWhiteSpace(segment) || segment == ".")
            {
                continue;
            }

            if (segment == "..")
            {
                if (segments.Count == 0)
                {
                    throw new InvalidDataException("An Office relationship points outside its package.");
                }

                segments.RemoveAt(segments.Count - 1);
                continue;
            }

            segments.Add(segment);
        }

        return string.Join('/', segments);
    }

    private static XDocument LoadXml(ZipArchive archive, string path)
    {
        var entry = archive.GetEntry(path)
            ?? throw new InvalidDataException($"The Office document is missing the '{path}' part.");
        return LoadXml(entry);
    }

    private static XDocument LoadXml(ZipArchiveEntry entry)
    {
        if (entry.Length > MaximumXmlCharacters)
        {
            throw new InvalidDataException("An Office XML part is too large to parse safely.");
        }

        var settings = new XmlReaderSettings
        {
            DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null,
            MaxCharactersInDocument = MaximumXmlCharacters,
            IgnoreComments = true,
            IgnoreProcessingInstructions = true
        };

        using var stream = entry.Open();
        using var reader = XmlReader.Create(stream, settings);
        return XDocument.Load(reader, LoadOptions.None);
    }

    private static string GetWordParagraphTag(string styleName)
    {
        if (styleName.Equals("Title", StringComparison.OrdinalIgnoreCase))
        {
            return "h1";
        }

        if (styleName.Equals("Subtitle", StringComparison.OrdinalIgnoreCase))
        {
            return "h3";
        }

        var normalizedStyle = styleName.Replace(" ", string.Empty, StringComparison.Ordinal);
        var heading = normalizedStyle.StartsWith("Heading", StringComparison.OrdinalIgnoreCase)
            ? normalizedStyle["Heading".Length..]
            : string.Empty;
        return int.TryParse(heading, out var level) && level is >= 1 and <= 6
            ? $"h{level}"
            : "p";
    }

    private static string BuildAlignmentStyle(string? alignment) =>
        alignment?.ToLowerInvariant() switch
        {
            "center" or "ctr" => "text-align:center",
            "right" or "end" or "r" => "text-align:right",
            "both" or "justify" or "just" => "text-align:justify",
            "left" or "start" or "l" => "text-align:left",
            _ => string.Empty
        };

    private static string? GetHighlightColor(string? value) =>
        value?.ToLowerInvariant() switch
        {
            "yellow" => "FFF2A8",
            "brightgreen" or "green" => "B7E1A1",
            "cyan" or "turquoise" => "A8E6E8",
            "magenta" or "pink" => "F4C4E6",
            "blue" => "B9D7F5",
            "red" => "F4B6B6",
            "darkblue" => "9EB7D8",
            "darkcyan" => "9BC9C9",
            "darkgreen" => "A5C7A5",
            "darkmagenta" => "D8A6D0",
            "darkred" => "D9A0A0",
            "darkyellow" => "E9D68A",
            "lightgray" or "lightgrey" => "E5E7EB",
            "darkgray" or "darkgrey" => "A3A3A3",
            "black" => "9CA3AF",
            _ => null
        };

    private static bool ContainsArabic(string value) =>
        value.Any(character =>
            character is >= '\u0600' and <= '\u06FF' ||
            character is >= '\u0750' and <= '\u077F' ||
            character is >= '\u08A0' and <= '\u08FF' ||
            character is >= '\uFB50' and <= '\uFDFF' ||
            character is >= '\uFE70' and <= '\uFEFF');

    private static string? NormalizeHexColor(string? color)
    {
        if (string.IsNullOrWhiteSpace(color) ||
            color.Equals("auto", StringComparison.OrdinalIgnoreCase) ||
            color.Equals("none", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        var normalized = color.Trim().TrimStart('#');
        return normalized.Length == 6 && normalized.All(Uri.IsHexDigit)
            ? normalized.ToUpperInvariant()
            : null;
    }

    private static double? ParsePositiveNumber(string? value) =>
        double.TryParse(
            value,
            System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture,
            out var parsed) && double.IsFinite(parsed) && parsed > 0
            ? parsed
            : null;

    private static double? ParsePositiveOrSignedNumber(string? value) =>
        double.TryParse(
            value,
            System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture,
            out var parsed) && double.IsFinite(parsed)
            ? parsed
            : null;

    private static void TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
        }
        catch
        {
            // The next launch can remove an abandoned preview directory.
        }
    }

    private sealed record RelationshipTarget(string Target);
}
