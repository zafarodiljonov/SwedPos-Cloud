using System.Globalization;

namespace SwedPos.Cloud;

/// <summary>Uzbek and Russian texts. The language is part of the address: /uz/... or /ru/...</summary>
public static partial class Texts
{
    public static string Normalize(string? lang) => lang == "ru" ? "ru" : "uz";

    public static string Get(string lang, string key) =>
        All.TryGetValue(key, out var t) || Own.TryGetValue(key, out t) ? (lang == "ru" ? t.Ru : t.Uz) : key;

    /// <summary>Website-only texts added after the copy from the desktop.</summary>
    private static readonly Dictionary<string, (string Uz, string Ru)> Own = new()
    {
        ["web_try_demo"] = ("Demoni ochish", "Открыть демо"),
    };
}

/// <summary>Number formats as in the desktop app: "1 250 000", short axis labels "1,2 mln".</summary>
public static class Fmt
{
    public static readonly CultureInfo Culture = MakeCulture();

    private static CultureInfo MakeCulture()
    {
        var c = (CultureInfo)CultureInfo.InvariantCulture.Clone();
        c.NumberFormat.NumberGroupSeparator = " ";
        c.NumberFormat.NumberDecimalSeparator = ",";
        return c;
    }

    public static string Money(decimal v) => v.ToString("#,0", Culture);
    public static string Int(decimal v) => v.ToString("#,0", Culture);
    public static string Percent(decimal v) => v.ToString("0.#", Culture) + "%";

    public static string Short(decimal v, string lang)
    {
        var a = Math.Abs(v);
        if (a >= 1_000_000_000) return (v / 1_000_000_000).ToString("0.#", Culture) + " " + Texts.Get(lang, "an_bln");
        if (a >= 1_000_000) return (v / 1_000_000).ToString("0.#", Culture) + " " + Texts.Get(lang, "an_mln");
        if (a >= 1_000) return (v / 1_000).ToString("0.#", Culture) + " " + Texts.Get(lang, "an_thousand");
        return v.ToString("0", Culture);
    }
}
