from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.forms import ModelForm, TextInput, EmailInput, PasswordInput

from coffee_shop.apps.catalog.models import Category, Product
from coffee_shop.apps.orders.models import Order


def home(request):
    """Home page with banners, hits, promotions."""
    products = Product.objects.filter(is_available=True)[:8]
    categories = Category.objects.filter(is_active=True)
    return render(request, 'home.html', {
        'products': products,
        'categories': categories,
    })


def about(request):
    """About page with history, contacts, map."""
    return render(request, 'about.html')


def json_response(data, status=200):
    """Helper to create JSON responses."""
    return JsonResponse(data, status=status)


def health_check(request):
    """Health check endpoint for Docker and monitoring."""
    return JsonResponse({
        'status': 'ok',
        'timestamp': timezone.now().isoformat(),
    })


class UserUpdateForm(ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        widgets = {
            'first_name': TextInput(attrs={'class': 'form-control'}),
            'last_name': TextInput(attrs={'class': 'form-control'}),
            'username': TextInput(attrs={'class': 'form-control'}),
            'email': EmailInput(attrs={'class': 'form-control'}),
        }


def dashboard_view(request):
    """Личный кабинет — история заказов."""
    if not request.user.is_authenticated:
        return redirect('login')

    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'dashboard.html', {'orders': orders})


def profile_view(request):
    """Редактирование профиля."""
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method == 'POST':
        form = UserUpdateForm(instance=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль обновлён')

            # Change password if requested
            pw_current = request.POST.get('password_current')
            pw_new = request.POST.get('password_new')
            pw_confirm = request.POST.get('password_confirm')

            if pw_new or pw_confirm:
                if request.user.check_password(pw_current):
                    if pw_new == pw_confirm and len(pw_new) >= 6:
                        request.user.set_password(pw_new)
                        request.user.save()
                        messages.success(request, 'Пароль обновлён')
                    else:
                        messages.error(request, 'Пароли не совпадают')
                else:
                    messages.error(request, 'Неверный текущий пароль')

            return redirect('profile')
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'profile.html', {
        'user_form': form,
        'addresses': [],
    })


def news_view(request):
    """Страница новостей."""
    from coffee_shop.apps.news.models import News
    from django.utils import timezone
    
    news = News.objects.filter(
        is_published=True,
        published_at__lte=timezone.now()
    ).order_by('-published_at')[:10]
    
    return render(request, 'news.html', {
        'news': news,
    })
