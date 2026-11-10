namespace SwedPos.Cloud.Reports;

public static class ChartMath
{
    /// <summary>A rounded-up axis maximum and step (1, 2, 2.5, 5 x 10^n) so grid lines fall on readable values.</summary>
    public static (decimal Max, decimal Step) NiceScale(decimal max, int lines = 4)
    {
        if (max <= 0) return (lines, 1);
        var raw = (double)max / lines;
        var magnitude = Math.Pow(10, Math.Floor(Math.Log10(raw)));
        var step = new[] { 1, 2, 2.5, 5, 10 }.Select(m => m * magnitude).First(s => s >= raw);
        return ((decimal)(step * lines), (decimal)step);
    }

    /// <summary>Only local paths, so the language switch cannot send anyone to another site.</summary>
    public static string SafeLocal(string? path) =>
        !string.IsNullOrEmpty(path) && path.StartsWith('/') && !path.StartsWith("//") && !path.StartsWith("/\\") ? path : "/";
}
