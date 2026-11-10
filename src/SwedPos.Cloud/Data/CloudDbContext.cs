using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace SwedPos.Cloud.Data;

/// <summary>A restaurant connected to SwedPos Cloud. Its sales live in a database of its own (see TenantDatabases).</summary>
public class Restaurant
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    /// <summary>SHA-256 of the sync key; the key itself is shown once, when the restaurant is created.</summary>
    public string KeyHash { get; set; } = "";
    /// <summary>First characters of the key, to recognise it without storing it.</summary>
    public string KeyPrefix { get; set; } = "";
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? LastSyncAt { get; set; }
    public string? LastAppVersion { get; set; }
    public bool IsActive { get; set; } = true;
}

/// <summary>A person who logs in to the website (the owner, a manager). Logs in with phone number and password.</summary>
public class Account
{
    public int Id { get; set; }
    /// <summary>Digits only, with country code: 998901234567.</summary>
    public string Phone { get; set; } = "";
    public string Name { get; set; } = "";
    public string PasswordHash { get; set; } = "";
    /// <summary>SwedPos staff: sees every restaurant and can add restaurants and accounts.</summary>
    public bool IsAdmin { get; set; }
    public bool IsActive { get; set; } = true;
    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    public DateTime? LastLoginAt { get; set; }
    public List<AccountRestaurant> Restaurants { get; set; } = new();
}

/// <summary>Which restaurants an account may see.</summary>
public class AccountRestaurant
{
    public int AccountId { get; set; }
    public int RestaurantId { get; set; }
    public Restaurant Restaurant { get; set; } = null!;
}

public class CloudDbContext : DbContext
{
    public CloudDbContext(DbContextOptions<CloudDbContext> options) : base(options) { }

    public DbSet<Restaurant> Restaurants => Set<Restaurant>();
    public DbSet<Account> Accounts => Set<Account>();
    public DbSet<AccountRestaurant> AccountRestaurants => Set<AccountRestaurant>();

    protected override void OnModelCreating(ModelBuilder b)
    {
        b.Entity<Restaurant>().HasIndex(r => r.KeyHash).IsUnique();
        b.Entity<Restaurant>().Property(r => r.Name).HasMaxLength(120);
        b.Entity<Account>().HasIndex(a => a.Phone).IsUnique();
        b.Entity<Account>().Property(a => a.Phone).HasMaxLength(20);
        b.Entity<AccountRestaurant>().HasKey(x => new { x.AccountId, x.RestaurantId });
        b.Entity<Account>().HasMany(a => a.Restaurants).WithOne().HasForeignKey(x => x.AccountId);
    }
}

/// <summary>Lets "dotnet ef migrations add" build the context without the running site.</summary>
public class CloudDbContextFactory : IDesignTimeDbContextFactory<CloudDbContext>
{
    public CloudDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<CloudDbContext>().UseNpgsql("Host=localhost;Database=swedpos_cloud").Options);
}
