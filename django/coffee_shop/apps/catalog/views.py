"""Catalog views."""
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from .models import Category, Product
from .services.coffee_service import CoffeeService


def catalog(request):
    """Каталог товаров с фильтрами."""
    categories = Category.objects.filter(is_active=True)
    products = Product.objects.filter(is_available=True)

    # Фильтры
    category_id = request.GET.get('category')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    roast_level = request.GET.get('roast')
    sca_min = request.GET.get('sca_min')

    if category_id:
        products = products.filter(category_id=category_id)
    if min_price:
        products = products.filter(price_per_50g__gte=min_price)
    if max_price:
        products = products.filter(price_per_50g__lte=max_price)
    if roast_level:
        products = products.filter(roast_level=roast_level)
    if sca_min:
        products = products.filter(sca_score__gte=sca_min)

    context = {
        'categories': categories,
        'products': products,
        'min_price': min_price,
        'max_price': max_price,
        'roast_level': roast_level,
        'sca_min': sca_min,
    }
    return render(request, 'catalog.html', context)


def product_detail(request, slug):
    """Карточка товара."""
    product = get_object_or_404(Product, slug=slug, is_available=True)
    
    available_weights = CoffeeService.get_available_weights(product)
    
    # Похожие товары
    related = Product.objects.filter(
        category=product.category,
        is_available=True
    ).exclude(slug=slug)[:4]

    context = {
        'product': product,
        'available_weights': available_weights,
        'related_products': related,
    }
    return render(request, 'product_detail.html', context)



