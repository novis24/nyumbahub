from django.db import migrations
from django.utils.text import slugify


TAXONOMY = {
    'Groceries & Food': ['Fresh Produce', 'Grains & Staples', 'Beverages', 'Snacks', 'Prepared Foods'],
    'Fashion & Clothing': ['Women Clothing', 'Men Clothing', 'Kids Clothing', 'Traditional Wear', 'Uniforms'],
    'Shoes & Bags': ['Women Shoes', 'Men Shoes', 'Bags', 'Backpacks', 'Wallets'],
    'Beauty & Personal Care': ['Hair Care', 'Skin Care', 'Makeup', 'Fragrances', 'Salon Supplies'],
    'Health Products': ['Supplements', 'Personal Care', 'Medical Supplies', 'Wellness'],
    'Phones & Tablets': ['Smartphones', 'Tablets', 'Phone Accessories', 'Repairs'],
    'Computers & Accessories': ['Laptops', 'Desktops', 'Printers', 'Networking', 'Computer Accessories'],
    'Electronics': ['TV & Audio', 'Cameras', 'Gaming', 'Power & Solar', 'Accessories'],
    'Home Appliances': ['Refrigerators', 'Cookers', 'Washing Machines', 'Small Appliances'],
    'Furniture & Décor': ['Living Room', 'Bedroom', 'Office Furniture', 'Decor', 'Outdoor'],
    'Kitchen & Dining': ['Cookware', 'Dinnerware', 'Storage', 'Kitchen Tools'],
    'Cleaning & Laundry': ['Detergents', 'Cleaning Tools', 'Laundry Supplies', 'Sanitation'],
    'Tools & Hardware': ['Hand Tools', 'Power Tools', 'Electrical', 'Plumbing', 'Safety Gear'],
    'Building Materials': ['Cement & Blocks', 'Roofing', 'Paint', 'Timber', 'Tiles'],
    'Automotive Parts & Accessories': ['Spare Parts', 'Tyres', 'Oils & Fluids', 'Car Electronics', 'Motorcycle Parts'],
    'Agriculture & Farm Supplies': ['Seeds', 'Fertilizer', 'Farm Tools', 'Animal Feed', 'Irrigation'],
    'Baby & Kids': ['Baby Gear', 'Kids Clothing', 'Feeding', 'Diapers', 'School Items'],
    'Toys & Games': ['Educational Toys', 'Outdoor Toys', 'Board Games', 'Gaming Accessories'],
    'Books & Stationery': ['Books', 'Notebooks', 'Writing Supplies', 'Art Supplies'],
    'School & Office Supplies': ['Office Stationery', 'School Supplies', 'Office Equipment', 'Packaging'],
    'Sports & Fitness': ['Fitness Equipment', 'Sportswear', 'Team Sports', 'Outdoor Recreation'],
    'Jewellery & Watches': ['Jewellery', 'Watches', 'Accessories'],
    'Gifts & Crafts': ['Handmade Crafts', 'Gift Sets', 'Party Supplies', 'Souvenirs'],
    'Pet Supplies': ['Pet Food', 'Pet Care', 'Accessories'],
    'Industrial & Business Supplies': ['Machinery', 'Packaging', 'Wholesale Supplies', 'Safety Supplies'],
}


def seed_taxonomy(apps, schema_editor):
    ProductCategory = apps.get_model('listings', 'ProductCategory')
    for order, (name, subcategories) in enumerate(TAXONOMY.items(), start=1):
        parent, _ = ProductCategory.objects.get_or_create(
            slug=slugify(name),
            defaults={'name': name, 'order': order, 'is_active': True},
        )
        for sub_order, sub_name in enumerate(subcategories, start=1):
            ProductCategory.objects.get_or_create(
                slug=f'{parent.slug}-{slugify(sub_name)}',
                defaults={'name': sub_name, 'parent': parent, 'order': sub_order, 'is_active': True},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0008_listing_product_attributes_productcategory_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_taxonomy, migrations.RunPython.noop),
    ]
