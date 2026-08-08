"""Coffee service: validation and filtering."""
from typing import Optional
from ..models import Product


COFFEE_FORM_BEANS = 'beans'
COFFEE_FORM_GROUND = 'ground'


class CoffeeService:
    """Валидация параметров кофе."""

    @staticmethod
    def validate_weight(weight: int, max_stock: int) -> tuple[bool, Optional[str]]:
        """
        Проверка веса кофе.
        
        Args:
            weight: Вес в граммах
            max_stock: Максимальный остаток на складе
            
        Returns:
            (is_valid, error_message)
        """
        if weight is None or weight <= 0:
            return False, 'Укажите вес'
        
        if weight % 50 != 0:
            return False, 'Вес должен быть кратен 50 г'
        
        if weight > max_stock:
            return False, f'Доступно не более {max_stock} г'
        
        return True, None

    @staticmethod
    def validate_brewing_method(
        coffee_form: str,
        brewing_method: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        """
        Проверка способа заваривания.
        
        Args:
            coffee_form: Форма кофе (beans/ground)
            brewing_method: Способ заваривания (nullable)
            
        Returns:
            (is_valid, error_message)
        """
        if coffee_form == COFFEE_FORM_BEANS:
            # При зёрнах способ заваривания не нужен
            return True, None
        
        if coffee_form == COFFEE_FORM_GROUND:
            if not brewing_method:
                return False, 'Укажите способ заваривания'
            return True, None
        
        return False, 'Неверная форма кофе'

    @staticmethod
    def validate_all(
        product: Product,
        weight: int,
        coffee_form: str,
        brewing_method: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """Полная валидация параметров кофе."""
        # Валидация веса
        is_valid, error = CoffeeService.validate_weight(weight, product.stock)
        if not is_valid:
            return False, error
        
        # Валидация формы
        if coffee_form not in [COFFEE_FORM_BEANS, COFFEE_FORM_GROUND]:
            return False, 'Неверная форма кофе'
        
        # Валидация способа заваривания
        is_valid, error = CoffeeService.validate_brewing_method(
            coffee_form, brewing_method
        )
        if not is_valid:
            return False, error
        
        # Если молотый — проверяем что метод есть в available_brewing_methods
        if coffee_form == COFFEE_FORM_GROUND and product.available_brewing_methods:
            if brewing_method not in product.available_brewing_methods:
                return False, 'Выбранный способ заваривания недоступен для этого товара'
        
        return True, None

    @staticmethod
    def get_available_weights(product: Product) -> list[int]:
        """Доступные веса (кратность 50 г, не больше stock)."""
        if product.stock <= 0:
            return []
        
        max_weight = product.stock
        # Ограничим максимум 1000 г (чтобы не было 10000 г для мелкого товара)
        max_weight = min(max_weight, 1000)
        
        weights = []
        for w in range(50, max_weight + 1, 50):
            weights.append(w)
        
        return weights
