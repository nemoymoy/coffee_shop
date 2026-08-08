"""Coffee pricing calculation."""
from decimal import Decimal


def coffee_price(weight_grams: int, price_per_50g: Decimal) -> Decimal:
    """
    Расчёт стоимости кофе.
    
    Формула: (weight / 50) * price_per_50g
    
    Args:
        weight_grams: Вес в граммах (кратно 50)
        price_per_50g: Цена за 50 граммов
        
    Returns:
        Итоговая цена
    """
    if weight_grams <= 0:
        return Decimal('0.00')
    
    units = weight_grams // 50
    return units * price_per_50g
