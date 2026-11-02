from flask import Blueprint, current_app, g, jsonify, request
from .common import json_body, ok
from ..services.placement_diagnosis import PlacementDiagnosisService
from ..services.smart_placement import PlacementChangeConflict, SmartPlacementUnavailable


def register_routes(api: Blueprint):
    def handle(action):
        try:
            return ok(action())
        except PermissionError as error:
            return jsonify(success=False, message=str(error), data=None), 403
        except PlacementChangeConflict as error:
            return jsonify(success=False, message=str(error), data=None), 409
        except ValueError as error:
            return jsonify(success=False, message=str(error), data=None), 400
        except SmartPlacementUnavailable as error:
            return jsonify(success=False, message=str(error), data=None), 503

    @api.get('/v1/smart-placement/route-diagnosis')
    def placement_route_diagnosis():
        return handle(lambda: PlacementDiagnosisService(current_app.config).list(g.current_user, request.args))

    @api.post('/v1/smart-placement/tasks/<int:task_id>/route-followups')
    def placement_route_followup(task_id):
        return handle(lambda: PlacementDiagnosisService(current_app.config).followup(g.current_user, task_id, json_body()))
