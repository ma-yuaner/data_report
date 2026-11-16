"""Asset metadata endpoints; existing data_assets menu and explicit inventory permission."""
from functools import wraps

from flask import current_app, g, jsonify, request

from .common import json_body, ok
from ..services.asset_inventory import AssetInventory, InventoryError
from ..shared.permissions import permission_codes


def _call(write=False):
    def decorate(function):
        @wraps(function)
        def wrapped():
            user = g.current_user
            permissions = permission_codes(user)
            can_read = bool(user.get("is_admin")) or ("data_assets" in set(user.get("menu_codes") or []) and "assets.inventory.view" in permissions)
            can_write = can_read and (bool(user.get("is_admin")) or "assets.dictionary.manage" in permissions)
            if not can_read or (write and not can_write):
                return jsonify(success=False, data=None, code="ASSET_FORBIDDEN", message="当前账号没有完整资产目录或字典维护权限"), 403
            try:
                return ok(function(AssetInventory(current_app.config), user, can_write))
            except InventoryError as error:
                return jsonify(success=False, data=None, code=error.code, message=error.message), error.status
            except ValueError as error:
                return jsonify(success=False, data=None, code="ASSET_INVALID", message=str(error)), 400
        return wrapped
    return decorate


def register_routes(api):
    @api.get("/v1/assets/inventory/summary")
    @_call()
    def asset_inventory_summary(service, user, can_write):
        return {**service.summary(), "canManageDictionary": can_write}

    @api.get("/v1/assets/inventory/objects")
    @_call()
    def asset_inventory_objects(service, user, can_write):
        return service.objects(request.args)

    @api.get("/v1/assets/inventory/detail")
    @_call()
    def asset_inventory_detail(service, user, can_write):
        return service.detail(request.args.get("assetId"), request.args.get("version"), can_write)

    @api.get("/v1/assets/inventory/lineage")
    @_call()
    def asset_inventory_lineage(service, user, can_write):
        return service.lineage(request.args.get("assetId"), request.args)

    @api.get("/v1/assets/inventory/gaps")
    @_call()
    def asset_inventory_gaps(service, user, can_write):
        return service.gaps(request.args)

    @api.put("/v1/assets/inventory/dictionary")
    @_call(write=True)
    def asset_inventory_dictionary_save(service, user, can_write):
        body = json_body()
        return service.save_dictionary(body.get("assetId"), body, user)

    @api.post("/v1/assets/inventory/dictionary/publish")
    @_call(write=True)
    def asset_inventory_dictionary_publish(service, user, can_write):
        body = json_body()
        return service.save_dictionary(body.get("assetId"), body, user, publish=True)
