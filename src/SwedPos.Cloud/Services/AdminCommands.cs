using Microsoft.EntityFrameworkCore;
using SwedPos.Cloud.Data;
using SwedPos.Services;

namespace SwedPos.Cloud.Services;

/// <summary>
/// Commands for SwedPos staff, run on the cloud server:
///   dotnet run -- add-restaurant "Marokand"
///   dotnet run -- add-account 998901234567 "Owner name" "password" 1[,2] [admin]
///   dotnet run -- renew-key 1
///   dotnet run -- list
/// </summary>
public static class AdminCommands
{
    public static async Task<bool> RunAsync(WebApplication app, string[] args)
    {
        var command = args[0];
        if (command is not ("add-restaurant" or "add-account" or "renew-key" or "list")) return false;

        using var scope = app.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<CloudDbContext>();
        await db.Database.MigrateAsync();
        var accounts = scope.ServiceProvider.GetRequiredService<CloudAccounts>();
        try
        {
            switch (command)
            {
                case "add-restaurant" when args.Length >= 2:
                {
                    var (r, key) = await accounts.AddRestaurantAsync(args[1]);
                    Console.WriteLine($"Restaurant {r.Id}: {r.Name}");
                    Console.WriteLine($"Sync key (shown only now, paste it into SwedPos > Settings > SwedPos Cloud on the server PC):");
                    Console.WriteLine(key);
                    break;
                }
                case "add-account" when args.Length >= 5:
                {
                    var ids = args[4].Split(',', StringSplitOptions.RemoveEmptyEntries).Select(int.Parse).ToList();
                    var a = await accounts.SaveAccountAsync(args[1], args[2], args[3], args.Length > 5 && args[5] == "admin", ids);
                    Console.WriteLine($"Account {a.Id}: {a.Name} ({a.Phone}), restaurants {string.Join(",", ids)}{(a.IsAdmin ? ", admin" : "")}");
                    break;
                }
                case "renew-key" when args.Length >= 2:
                    Console.WriteLine("New sync key: " + await accounts.RenewKeyAsync(int.Parse(args[1])));
                    break;
                case "list":
                    foreach (var r in await db.Restaurants.OrderBy(r => r.Id).ToListAsync())
                        Console.WriteLine($"{r.Id}\t{r.Name}\tkey {r.KeyPrefix}…\tlast sync {r.LastSyncAt:yyyy-MM-dd HH:mm} UTC\tapp {r.LastAppVersion}");
                    foreach (var a in await db.Accounts.Include(a => a.Restaurants).OrderBy(a => a.Id).ToListAsync())
                        Console.WriteLine($"account {a.Id}\t{a.Phone}\t{a.Name}\trestaurants {string.Join(",", a.Restaurants.Select(x => x.RestaurantId))}{(a.IsAdmin ? "\tadmin" : "")}");
                    break;
                default:
                    Console.WriteLine("Wrong arguments. See AdminCommands.cs.");
                    break;
            }
        }
        catch (ValidationException ex) { Console.WriteLine("Error: " + ex.Message); }
        return true;
    }
}
