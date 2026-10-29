// Generated from src/layouts/AppLayout.vue by generate-system-navigation.mjs. Do not hand-edit.
export interface SystemMenuNode { id:string; title:string; route:string; disabled:boolean; children:SystemMenuNode[] }
export const systemMenus: SystemMenuNode[] = [
  {
    "id": "/home",
    "title": "工作台",
    "route": "/home",
    "disabled": false,
    "children": []
  },
  {
    "id": "governance",
    "title": "资源治理",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/resource-governance/gds",
        "title": "GDS资源治理",
        "route": "/resource-governance/gds",
        "disabled": false,
        "children": []
      },
      {
        "id": "/resource-governance/ota",
        "title": "OTA渠道质量",
        "route": "/resource-governance/ota",
        "disabled": false,
        "children": []
      },
      {
        "id": "/resource-governance/route-diagnosis",
        "title": "航线配置诊断",
        "route": "/resource-governance/route-diagnosis",
        "disabled": false,
        "children": []
      },
      {
        "id": "/resource-governance/whitelist",
        "title": "白名单管理",
        "route": "/resource-governance/whitelist",
        "disabled": false,
        "children": []
      },
      {
        "id": "/resource-governance/execution",
        "title": "治理执行",
        "route": "/resource-governance/execution",
        "disabled": false,
        "children": []
      },
      {
        "id": "/resource-governance/review",
        "title": "治理复盘",
        "route": "/resource-governance/review",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "/overview",
    "title": "经营总览",
    "route": "/overview",
    "disabled": false,
    "children": []
  },
  {
    "id": "analysis",
    "title": "业务分析",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/analysis/comprehensive",
        "title": "综合分析",
        "route": "/analysis/comprehensive",
        "disabled": false,
        "children": []
      },
      {
        "id": "/analysis/issue",
        "title": "出票分析",
        "route": "/analysis/issue",
        "disabled": false,
        "children": []
      },
      {
        "id": "/analysis/refund",
        "title": "退票分析",
        "route": "/analysis/refund",
        "disabled": false,
        "children": []
      },
      {
        "id": "/analysis/change",
        "title": "改签分析",
        "route": "/analysis/change",
        "disabled": false,
        "children": []
      },
      {
        "id": "/analysis/ancillary",
        "title": "增值分析",
        "route": "/analysis/ancillary",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "risk",
    "title": "风控分析",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/risk-analysis",
        "title": "风控总览",
        "route": "/risk-analysis",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/issue",
        "title": "出票利润分析",
        "route": "/risk-analysis/issue",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/refund",
        "title": "退票利润分析",
        "route": "/risk-analysis/refund",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/change",
        "title": "改签利润分析",
        "route": "/risk-analysis/change",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/errors",
        "title": "差错分析",
        "route": "/risk-analysis/errors",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/orders",
        "title": "订单明细",
        "route": "/risk-analysis/orders",
        "disabled": false,
        "children": []
      },
      {
        "id": "/risk-analysis/upload",
        "title": "数据上传",
        "route": "/risk-analysis/upload",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "customer-service",
    "title": "客服分析",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "customer-service-refund",
        "title": "退票分析",
        "route": "",
        "disabled": true,
        "children": []
      },
      {
        "id": "customer-service-change",
        "title": "改签分析",
        "route": "",
        "disabled": true,
        "children": []
      },
      {
        "id": "customer-service-flight-change",
        "title": "清Q/航变分析",
        "route": "",
        "disabled": true,
        "children": []
      }
    ]
  },
  {
    "id": "smart",
    "title": "智能分析",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "smart-overall",
        "title": "智能整体分析",
        "route": "",
        "disabled": false,
        "children": [
          {
            "id": "/smart-analysis/comprehensive",
            "title": "综合分析",
            "route": "/smart-analysis/comprehensive",
            "disabled": false,
            "children": []
          },
          {
            "id": "/smart-analysis/overview",
            "title": "智能总览",
            "route": "/smart-analysis/overview",
            "disabled": false,
            "children": []
          },
          {
            "id": "/smart-analysis/dimensions",
            "title": "维度分析",
            "route": "/smart-analysis/dimensions",
            "disabled": false,
            "children": []
          },
          {
            "id": "/smart-analysis/details",
            "title": "出票明细",
            "route": "/smart-analysis/details",
            "disabled": false,
            "children": []
          }
        ]
      },
      {
        "id": "smart-placement",
        "title": "智能投放",
        "route": "",
        "disabled": false,
        "children": [
          {
            "id": "/smart-analysis/placement/policies",
            "title": "投放政策",
            "route": "/smart-analysis/placement/policies",
            "disabled": false,
            "children": []
          },
          {
            "id": "/smart-analysis/placement/orders",
            "title": "收单情况",
            "route": "/smart-analysis/placement/orders",
            "disabled": false,
            "children": []
          }
        ]
      }
    ]
  },
  {
    "id": "business-configuration",
    "title": "业务配置",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/business-configuration/targets",
        "title": "目标配置",
        "route": "/business-configuration/targets",
        "disabled": false,
        "children": []
      },
      {
        "id": "/business-configuration/target-progress",
        "title": "目标进度",
        "route": "/business-configuration/target-progress",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "monitoring",
    "title": "监控中心",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/monitoring/overview",
        "title": "监控总览",
        "route": "/monitoring/overview",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/tasks",
        "title": "监控任务",
        "route": "/monitoring/tasks",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/alerts",
        "title": "预警中心",
        "route": "/monitoring/alerts",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/actions",
        "title": "技术工单",
        "route": "/monitoring/actions",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/templates",
        "title": "规则模板",
        "route": "/monitoring/templates",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/runs",
        "title": "监控运行",
        "route": "/monitoring/runs",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/notifications",
        "title": "通知管理",
        "route": "/monitoring/notifications",
        "disabled": false,
        "children": []
      },
      {
        "id": "/monitoring/diagnostics",
        "title": "问题诊断",
        "route": "/monitoring/diagnostics",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "adm",
    "title": "ADM 管理",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/adm/workbench",
        "title": "我的工作台",
        "route": "/adm/workbench",
        "disabled": false,
        "children": []
      },
      {
        "id": "/adm/cases",
        "title": "ADM 台账",
        "route": "/adm/cases",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "/problems",
    "title": "问题中心",
    "route": "/problems",
    "disabled": false,
    "children": []
  },
  {
    "id": "/data-assets",
    "title": "数据资产",
    "route": "/data-assets",
    "disabled": false,
    "children": []
  },
  {
    "id": "archived-features",
    "title": "归档功能",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/data-workbench",
        "title": "数据加工工作台",
        "route": "/data-workbench",
        "disabled": false,
        "children": []
      }
    ]
  },
  {
    "id": "/hr-mail",
    "title": "HR报表邮件",
    "route": "/hr-mail",
    "disabled": false,
    "children": []
  },
  {
    "id": "system",
    "title": "系统管理",
    "route": "",
    "disabled": false,
    "children": [
      {
        "id": "/admin/behavior",
        "title": "用户行为监控",
        "route": "/admin/behavior",
        "disabled": false,
        "children": []
      },
      {
        "id": "/admin/users",
        "title": "账号管理",
        "route": "/admin/users",
        "disabled": false,
        "children": []
      }
    ]
  }
]
export const systemMenuSource = 'src/layouts/AppLayout.vue'
