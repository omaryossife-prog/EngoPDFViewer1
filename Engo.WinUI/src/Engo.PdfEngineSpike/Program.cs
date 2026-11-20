using Aspose.Pdf;
using Aspose.Pdf.Devices;
using Aspose.Pdf.Text;

if (args.Length < 2)
{
    PrintUsage();
    return 2;
}

var inputPath = Path.GetFullPath(args[0]);
var renderOutputPath = Path.GetFullPath(args[1]);
var searchQuery = args.Length > 2 ? args[2] : string.Empty;

if (!File.Exists(inputPath))
{
    Console.Error.WriteLine($"Input PDF does not exist: {inputPath}");
    return 2;
}

try
{
    using var document = Document.Open(inputPath);

    Console.WriteLine($"Pages: {document.PageCount}");

    var textAbsorber = new TextAbsorber();
    textAbsorber.Visit(document);
    Console.WriteLine($"Extracted characters: {textAbsorber.Text.Length}");

    if (!string.IsNullOrWhiteSpace(searchQuery))
    {
        var searchAbsorber = new TextFragmentAbsorber(searchQuery);
        document.Pages.Accept(searchAbsorber);
        Console.WriteLine($"Search matches for '{searchQuery}': {searchAbsorber.TextFragments.Count}");
    }

    if (document.PageCount > 0)
    {
        var outputDirectory = Path.GetDirectoryName(renderOutputPath);
        if (!string.IsNullOrWhiteSpace(outputDirectory))
        {
            Directory.CreateDirectory(outputDirectory);
        }

        // Render one page per invocation to keep this smoke test bounded.
        var pageNumber = args.Length > 3 &&
                         int.TryParse(args[3], out var requestedPage)
            ? requestedPage
            : 1;

        if (pageNumber < 1 || pageNumber > document.PageCount)
        {
            Console.Error.WriteLine($"Page number must be between 1 and {document.PageCount}.");
            return 2;
        }

        var device = new PngDevice(new Resolution(144));
        device.Process(document.Pages[pageNumber], renderOutputPath);
        Console.WriteLine($"Rendered page {pageNumber}: {renderOutputPath}");
    }

    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine($"Aspose.PDF FOSS evaluation failed: {exception}");
    return 1;
}

static void PrintUsage()
{
    Console.WriteLine(
        "Usage: Engo.PdfEngineSpike <input.pdf> <output-page.png> [search-text] [page-number]");
}
