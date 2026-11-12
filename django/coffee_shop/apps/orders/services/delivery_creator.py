"""Yandex Delivery creation service — Express + Other Day APIs.

Unified service for creating delivery orders in Yandex Delivery.
Extracted from order_views.py to eliminate duplication across
checkout_view, payment_webhook, and payment_result.
"""
import json
import logging

from decimal import Decimal

from django.conf import settings

from coffee_shop.apps.orders.models import Package
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

logger = logging.getLogger(__name__)


class DeliveryCreator:
    """Unified service for creating Yandex Delivery orders.

    Handles both Express API (same-day courier) and Other Day API
    (PVZ/postamat with scheduled delivery intervals).
    """

    def __init__(self, order):
        self.order = order
        self.service = YandexDeliveryService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, address, coords, delivery_cost,
               existing_claim_id=None):
        """Create a delivery order in Yandex Delivery.

        Args:
            address: Full delivery address string.
            coords: [longitude, latitude] list.
            delivery_cost: Decimal delivery cost in RUB.
            existing_claim_id: Optional Express claim ID from price calc.

        Returns:
            dict with 'success', 'claim_id'/'request_id', 'status', etc.
        """
        if not self.service.is_configured():
            logger.warning(
                '[DeliveryCreator] Yandex Delivery not configured for order %s',
                self.order.pk,
            )
            return {'success': False, 'error': 'Yandex Delivery not configured'}

        if self.order.delivery_api_type == 'express':
            return self._create_express(address, coords, existing_claim_id)
        else:
            return self._create_other_day(address, delivery_cost)

    # ------------------------------------------------------------------
    # Express API
    # ------------------------------------------------------------------

    def _create_express(self, address, coords, existing_claim_id):
        """Create or accept an Express delivery claim.

        If existing_claim_id is provided (from price calculation),
        checks status and accepts if not already accepted.
        Otherwise creates a new claim.

        Returns:
            {'success': True, 'claim_id': '...', 'status': '...'}
        """
        items, total_weight_kg = self._build_express_items()
        route_points = self._build_express_route_points(address, coords)

        if existing_claim_id:
            return self._accept_existing_express_claim(
                existing_claim_id, items, route_points
            )
        else:
            return self._create_new_express_claim(items, route_points)

    def _build_express_items(self):
        """Build Express API items payload from order."""
        total_weight_grams = 0
        total_quantity = 0
        product_name = 'Product'

        for oi in self.order.items.all():
            total_weight_grams += oi.weight_grams if oi.weight_grams else 0
            total_quantity += oi.quantity
            if oi.product:
                product_name = oi.product.name

        try:
            package = Package.for_weight(total_weight_grams)
            total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
            sz = {
                'length': float(package.length),
                'width': float(package.width),
                'height': float(package.height),
            }
        except Package.DoesNotExist:
            total_weight_kg = total_weight_grams / 1000.0 if total_weight_grams > 0 else 0.1
            sz = {'length': 0.12, 'width': 0.06, 'height': 0.06}

        item = {
            'title': product_name,
            'quantity': total_quantity,
            'cost_value': '0',
            'cost_currency': 'RUB',
            'pickup_point': 1,
            'droppof_point': 2,
            'size': sz,
            'weight': round(total_weight_kg, 3),
        }
        return [item], total_weight_kg

    def _build_express_route_points(self, address, coords):
        """Build Express API route_points payload."""
        return [
            {
                'point_id': 1,
                'visit_order': 1,
                'type': 'source',
                'contact': {
                    'name': 'Магазин',
                    'phone': '+79000000000',
                },
                'address': {
                    'fullname': self.service.shop_address,
                    'coordinates': [self.service.shop_lon, self.service.shop_lat],
                },
            },
            {
                'point_id': 2,
                'visit_order': 2,
                'type': 'destination',
                'contact': {
                    'name': self.order.recipient_name or 'Клиент',
                    'phone': self.order.recipient_phone or '',
                },
                'address': {
                    'fullname': address,
                    'coordinates': coords if coords else [49.35, 53.21],
                },
            },
        ]

    def _accept_existing_express_claim(self, claim_id, items, route_points):
        """Accept an existing Express claim if not already accepted."""
        logger.info('[DeliveryCreator/Express] Using existing claim_id: %s', claim_id)

        status_result = self.service.get_express_claim_info(claim_id)
        if not status_result.get('success'):
            # If we can't check status, try to accept anyway
            accept_result = self.service.accept_express_claim(claim_id)
            if accept_result.get('success'):
                return {
                    'success': True,
                    'claim_id': claim_id,
                    'status': accept_result.get('status', 'accepted'),
                }
            return {
                'success': False,
                'error': f'Failed to accept claim: {accept_result.get("error")}',
            }

        current_status = status_result.get('status', '')
        version = status_result.get('raw', {}).get('version', 1)
        logger.info(
            '[DeliveryCreator/Express] Existing claim status: %s, version: %d',
            current_status, version,
        )

        if current_status in ('confirmed', 'accepting', 'accepted'):
            logger.info('[DeliveryCreator/Express] Claim already accepted, skipping')
            return {
                'success': True,
                'claim_id': claim_id,
                'status': current_status,
            }

        accept_result = self.service.accept_express_claim(claim_id, version=version)
        if accept_result.get('success'):
            return {
                'success': True,
                'claim_id': claim_id,
                'status': accept_result.get('status', 'accepted'),
            }
        return {
            'success': False,
            'error': f'Failed to accept claim: {accept_result.get("error")}',
        }

    def _create_new_express_claim(self, items, route_points):
        """Create a new Express claim and accept it."""
        result = self.service.create_express_claim(
            items=items,
            route_points=route_points,
            client_requirements={'taxi_class': 'courier'},
        )
        if not result.get('success'):
            return result

        claim_id = result.get('claim_id')
        accept_result = self.service.accept_express_claim(claim_id)

        if accept_result.get('success'):
            return {
                'success': True,
                'claim_id': claim_id,
                'status': accept_result.get('status', 'accepted'),
            }
        return {
            'success': False,
            'error': f'Failed to accept claim: {accept_result.get("error")}',
        }

    # ------------------------------------------------------------------
    # Other Day API (PVZ / Postamat)
    # ------------------------------------------------------------------

    def _create_other_day(self, address, delivery_cost):
        """Create an Other Day delivery order (PVZ or postamat).

        Returns:
            {'success': True, 'request_id': '...', 'offer_id': '...',
             'tracking_number': '...', 'status': '...',
             'delivery_date': '...', 'delivery_time': '...',
             'price': '...'}
        """
        other_day_items, other_day_places = (
            self.service._build_items_payload_for_other_day(
                self.order.items.all(), pvz_id=self.order.pvz_id
            )
        )

        result = self.service.create_order(
            items=other_day_items,
            places=other_day_places,
            client_order_id=self.order.pk,
            destination_coords=[],
            destination_address=address,
            delivery_type=self.order.delivery_type,
            pvz_id=self.order.pvz_id,
            recipient_name=self.order.recipient_name,
            recipient_phone=self.order.recipient_phone,
            email=self.order.email,
            delivery_cost=float(delivery_cost),
            payment_method='already_paid',
        )

        if not result.get('success'):
            return result

        # Parse delivery interval from result
        self._parse_delivery_interval(result)

        # Update final price if available
        final_price = result.get('price')
        if final_price and final_price not in ('0', 'N/A', None):
            try:
                self.order.delivery_cost = Decimal(str(final_price))
                goods_total = sum(
                    (item.total_price for item in self.order.items.all()),
                    Decimal('0'),
                )
                self.order.total_amount = goods_total + self.order.delivery_cost
            except (ValueError, TypeError):
                logger.warning(
                    '[DeliveryCreator/OtherDay] Failed to parse final price: %s',
                    final_price,
                )

        return result

    @staticmethod
    def _parse_delivery_interval(result):
        """Parse delivery_date/delivery_time from Other Day API result.

        Updates result dict in-place with parsed fields.
        """
        delivery_date_str = result.get('delivery_date', '')
        delivery_time_str = result.get('delivery_time', '')

        if not delivery_date_str or not delivery_time_str:
            return

        try:
            from datetime import datetime as dt

            time_parts = delivery_time_str.split('–')
            if not time_parts:
                return

            date_part = dt.strptime(delivery_date_str, '%d.%m.%Y').date()
            time_from = dt.strptime(time_parts[0].strip(), '%H:%M').time()
            datetime_from = dt.combine(date_part, time_from)
            result['datetime_from'] = datetime_from

            if len(time_parts) > 1:
                time_to = dt.strptime(time_parts[1].strip(), '%H:%M').time()
                datetime_to = dt.combine(date_part, time_to)
                result['datetime_to'] = datetime_to
        except Exception as e:
            logger.warning(
                '[DeliveryCreator/OtherDay] Failed to parse delivery interval: %s', e
            )

    # ------------------------------------------------------------------
    # Result application helpers
    # ------------------------------------------------------------------

    @staticmethod
    def apply_express_result(order, result):
        """Apply Express API result to an Order instance."""
        order.express_claim_id = result.get('claim_id', '')
        order.yandex_order_id = order.express_claim_id
        yandex_status = result.get('status') or 'accepted'
        order.yandex_delivery_status = yandex_status.lower()
        order.yandex_delivery_status_raw = yandex_status

    @staticmethod
    def apply_other_day_result(order, result):
        """Apply Other Day API result to an Order instance."""
        order.yandex_offer_id = result.get('offer_id')
        order.yandex_order_id = result.get('request_id')
        order.tracking_number = result.get('tracking_number', '')
        yandex_status = result.get('status') or 'pending'
        order.yandex_delivery_status = yandex_status.lower()
        order.yandex_delivery_status_raw = yandex_status

        # Apply delivery interval if parsed
        dt_from = result.get('datetime_from')
        dt_to = result.get('datetime_to')
        if dt_from:
            order.delivery_interval_from = dt_from
        if dt_to:
            order.delivery_interval_to = dt_to

    @staticmethod
    def get_save_fields(order, result):
        """Determine which order fields to save after delivery creation."""
        fields = ['yandex_order_id', 'tracking_number', 'yandex_delivery_status']
        if order.yandex_delivery_status_raw:
            fields.append('yandex_delivery_status_raw')
        if order.express_claim_id:
            fields.append('express_claim_id')
        if order.yandex_offer_id:
            fields.append('yandex_offer_id')
        if order.delivery_interval_from or order.delivery_interval_to:
            fields.extend(['delivery_interval_from', 'delivery_interval_to'])
        return fields

    # ------------------------------------------------------------------
    # Payment webhook / payment_result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def accept_express_claim_for_paid(order):
        """Accept an existing Express claim for a paid order.

        Called from payment_webhook and payment_result after payment confirmation.
        """
        service = YandexDeliveryService()
        if not service.is_configured():
            return None

        claim_id = order.express_claim_id
        if not claim_id:
            return None

        logger.info('[DeliveryCreator] Accepting Express claim %s for paid order %s',
                    claim_id, order.pk)

        info = service.get_express_claim_info(claim_id)
        version = info.get('raw', {}).get('version', 1) if info.get('success') else 1
        accept_result = service.accept_express_claim(claim_id, version=version)

        if accept_result.get('success'):
            order.yandex_order_id = claim_id
            order.yandex_delivery_status = accept_result.get('status', 'accepted').lower()
            order.yandex_delivery_status_raw = accept_result.get('status', 'accepted')
            logger.info('[DeliveryCreator] Express claim accepted: %s',
                        accept_result.get('status'))
            return accept_result
        else:
            logger.error('[DeliveryCreator] Failed to accept Express claim: %s',
                         accept_result.get('error'))
            return None

    @staticmethod
    def create_other_day_for_paid(order):
        """Create an Other Day delivery for a paid order.

        Called from payment_webhook and payment_result after payment confirmation.
        """
        service = YandexDeliveryService()
        if not service.is_configured():
            return None

        other_day_items, other_day_places = (
            service._build_items_payload_for_other_day(
                order.items.all(), pvz_id=order.pvz_id
            )
        )

        result = service.create_order(
            items=other_day_items,
            places=other_day_places,
            client_order_id=order.pk,
            destination_coords=[],
            destination_address=order.delivery_address,
            delivery_type=order.delivery_type,
            pvz_id=order.pvz_id,
            recipient_name=order.recipient_name,
            recipient_phone=order.recipient_phone,
            email=order.email,
            delivery_cost=float(order.delivery_cost),
            payment_method='already_paid',
        )

        if not result.get('success'):
            logger.error('[DeliveryCreator] Failed to create Other Day order for order %s: %s',
                         order.pk, result.get('error'))
            return result

        # Parse delivery interval
        DeliveryCreator._parse_delivery_interval(result)

        # Update final price
        final_price = result.get('price')
        if final_price and final_price not in ('0', 'N/A', None):
            try:
                order.delivery_cost = Decimal(str(final_price))
                goods_total = sum(
                    (item.total_price for item in order.items.all()),
                    Decimal('0'),
                )
                order.total_amount = goods_total + order.delivery_cost
            except (ValueError, TypeError):
                logger.warning('[DeliveryCreator] Failed to parse final price: %s', final_price)

        # Apply result to order
        DeliveryCreator.apply_other_day_result(order, result)

        return result
