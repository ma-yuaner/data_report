from flask import Blueprint, current_app, g, jsonify, request

from .common import ok
from ..services.missed_orders import MissedOrdersService, MissedOrdersUnavailable, MissedOrderNotFound


def register_routes(api: Blueprint) -> None:
    def respond(action):
        try:
            return ok(action(MissedOrdersService(current_app.config)))
        except PermissionError as error:
            return jsonify(success=False,message=str(error),data=None),403
        except MissedOrderNotFound as error:
            return jsonify(success=False,message=str(error),data=None),404
        except ValueError as error:
            return jsonify(success=False,message=str(error),data=None),400
        except MissedOrdersUnavailable as error:
            return jsonify(success=False,message=str(error),data=None),503

    @api.get('/v1/smart-placement/missed-orders')
    def missed_order_list():
        return respond(lambda service: service.list(g.current_user,request.args.to_dict()))

    @api.get('/v1/smart-placement/missed-orders/options')
    def missed_order_options():
        return respond(lambda service: service.options(g.current_user,request.args.to_dict()))

    @api.get('/v1/smart-placement/missed-orders/<int:record_id>')
    def missed_order_detail(record_id: int):
        def detail(service):
            from ..services.smart_placement import SmartPlacementService, SmartPlacementUnavailable
            result = service.detail(g.current_user,record_id)
            user = g.current_user
            if user.get('is_admin') or 'smart.placement.orders' in (user.get('menu_codes') or []):
                try:
                    result['matches'] = SmartPlacementService(current_app.config).related_order_matches(user,result['row']['otaOrderNo'],result['row']['platformName'])
                except (PermissionError,SmartPlacementUnavailable) as error:
                    result['matches'] = {'available':False,'rows':[],'message':str(error)}
            else:
                result['matches'] = {'available':False,'rows':[],'message':'当前账号无收单情况权限，未读取投放关联。'}
            return result
        return respond(detail)
