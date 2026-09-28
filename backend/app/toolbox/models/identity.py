"""Upstream identity models; toolbox never defines another credential table."""
from app.modules.system.dept.model import DeptModel
from app.modules.system.position.model import PositionModel
from app.modules.system.menu.model import MenuModel
from app.modules.system.role.model import RoleModel, RoleMenusModel, RoleDeptsModel
from app.modules.system.user.model import UserModel, UserRolesModel, UserPositionsModel
from app.modules.system.log.model import LoginLogModel, OperationLogModel
from app.modules.system.dict.model import DictDataModel, DictTypeModel
from app.modules.system.params.model import ParamsModel

User = UserModel
