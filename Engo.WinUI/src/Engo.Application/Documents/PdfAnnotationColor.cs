namespace Engo.Application.Documents;

public sealed record PdfAnnotationColor(
    double RedComponent,
    double GreenComponent,
    double BlueComponent)
{
    public static PdfAnnotationColor Yellow { get; } = new(1, 0.85, 0.1);
    public static PdfAnnotationColor Red { get; } = new(0.9, 0.12, 0.12);
    public static PdfAnnotationColor Blue { get; } = new(0.1, 0.32, 0.85);
    public static PdfAnnotationColor Green { get; } = new(0.1, 0.55, 0.28);
}
