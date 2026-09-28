"""Idempotently install the enabled upstream admin menus; never regrant roles."""
import json
from pathlib import Path
from sqlalchemy import select
from app.toolbox.models.identity import MenuModel
from app.modules.system.dict.model import DictTypeModel, DictDataModel


def seed_admin_ui(db):
    directory = Path(__file__).resolve().parents[3] / 'sql'
    source = json.loads((directory / 'sys_menu.json').read_text(encoding='utf-8'))
    system = next(item for item in source if item['route_name'] == 'System')
    enabled = {'menu', 'user', 'role', 'dept', 'position', 'dict', 'log'}
    system['children'] = [item for item in system['children'] if (item.get('route_path') or '').strip('/') in enabled]
    system['redirect'] = '/system/user'

    def add(item, parent_id=None):
        children = item.get('children', [])
        name, permission = item.get('route_name'), item.get('permission')
        query = select(MenuModel).where(MenuModel.route_name == name) if name else select(MenuModel).where(MenuModel.permission == permission)
        row = db.scalar(query)
        if row is None:
            values = {key: value for key, value in item.items() if key != 'children' and key in MenuModel.__table__.columns}
            row = MenuModel(**values, parent_id=parent_id)
            db.add(row); db.flush()
        for child in children: add(child, row.id)
    add(system)

    # Preserve upstream dictionary definitions, remapping FK IDs instead of assuming 1/2.
    definitions = json.loads((directory / 'sys_dict_type.json').read_text(encoding='utf-8'))
    data = json.loads((directory / 'sys_dict_data.json').read_text(encoding='utf-8'))
    for definition in definitions:
        kind = db.scalar(select(DictTypeModel).where(DictTypeModel.dict_type == definition['dict_type']))
        if kind is not None: continue  # Do not overwrite an administrator's customization.
        kind = DictTypeModel(**definition); db.add(kind); db.flush()
        for value in data:
            if value['dict_type'] == kind.dict_type:
                db.add(DictDataModel(**{**value, 'dict_type_id': kind.id}))
