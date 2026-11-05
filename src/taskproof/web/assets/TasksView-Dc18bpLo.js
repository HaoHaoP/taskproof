import { d as defineComponent, i as useBoardStore, u as useI18n, c as createElementBlock, b as createBaseVNode, t as toDisplayString, f as unref, g as createCommentVNode, e as createVNode, l as withCtx, h as computed, p as resolveComponent, v as useRouter, s as useRoute, o as openBlock, _ as _export_sfc } from "./index-CpE_Q7S0.js";
import { T as TaskDrawer, a as dispositionText, d as duration } from "./TaskDrawer-CnQkYf94.js";
const _hoisted_1 = { class: "tasks-view" };
const _hoisted_2 = { class: "panes" };
const _hoisted_3 = { class: "sub" };
const _hoisted_4 = { class: "taken" };
const _hoisted_5 = { class: "tp-table" };
const _hoisted_6 = ["data-status", "title"];
const _hoisted_7 = ["data-disposition", "title"];
const _hoisted_8 = ["title"];
const _hoisted_9 = ["title"];
const _hoisted_10 = ["title"];
const _hoisted_11 = ["title"];
const _hoisted_12 = ["title"];
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "TasksView",
  setup(__props) {
    const store = useBoardStore();
    const router = useRouter();
    const route = useRoute();
    const { t, te } = useI18n();
    const rows = computed(() => store.tasks);
    const TASK_COLUMN_WIDTHS = ["10%", "14%", "14%", "13%", "30%", "11%", "8%"];
    const tableStyle = {
      width: "100%",
      "--task-col-status": TASK_COLUMN_WIDTHS[0],
      "--task-col-dispo": TASK_COLUMN_WIDTHS[1],
      "--task-col-id": TASK_COLUMN_WIDTHS[2],
      "--task-col-project": TASK_COLUMN_WIDTHS[3],
      "--task-col-brief": TASK_COLUMN_WIDTHS[4],
      "--task-col-adapter": TASK_COLUMN_WIDTHS[5],
      "--task-col-duration": TASK_COLUMN_WIDTHS[6]
    };
    function reasonTitle(value) {
      return value?.trim() || void 0;
    }
    function open(id) {
      void router.push({ name: "tasks", params: { taskId: id }, query: route.query });
    }
    return (_ctx, _cache) => {
      const _component_el_table_column = resolveComponent("el-table-column");
      const _component_el_table = resolveComponent("el-table");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createBaseVNode("div", _hoisted_2, [
          createBaseVNode("h3", null, toDisplayString(unref(t)("tasks.title")), 1),
          createBaseVNode("p", _hoisted_3, toDisplayString(unref(t)("tasks.sub")), 1),
          createBaseVNode("div", _hoisted_4, [
            createBaseVNode("span", null, toDisplayString(unref(t)("board.taken", { n: unref(store).tasks.length, m: unref(store).total })), 1),
            unref(store).tasks.length < unref(store).total ? (openBlock(), createElementBlock("button", {
              key: 0,
              type: "button",
              onClick: _cache[0] || (_cache[0] = ($event) => unref(store).growBudget())
            }, toDisplayString(unref(t)("board.takeMore")), 1)) : createCommentVNode("", true)
          ]),
          createBaseVNode("div", _hoisted_5, [
            createVNode(_component_el_table, {
              data: rows.value,
              style: tableStyle,
              onRowClick: _cache[1] || (_cache[1] = (row) => open(row.id))
            }, {
              default: withCtx(() => [
                createVNode(_component_el_table_column, {
                  label: unref(t)("status.label"),
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "sc",
                      "data-status": scope.row.status,
                      title: unref(t)(`status.${scope.row.status}`)
                    }, toDisplayString(unref(t)(`status.${scope.row.status}`)), 9, _hoisted_6)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.dispo"),
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "mono",
                      "data-disposition": scope.row.disposition,
                      title: reasonTitle(scope.row.disposition_reason)
                    }, toDisplayString(unref(dispositionText)(scope.row.disposition, unref(t), unref(te))), 9, _hoisted_7)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: "id",
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "mono",
                      title: scope.row.id
                    }, toDisplayString(scope.row.id), 9, _hoisted_8)
                  ]),
                  _: 1
                }),
                createVNode(_component_el_table_column, {
                  label: unref(t)("rail.title"),
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "mono muted",
                      title: scope.row.project
                    }, toDisplayString(scope.row.project), 9, _hoisted_9)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.brief"),
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      title: scope.row.brief
                    }, toDisplayString(scope.row.brief), 9, _hoisted_10)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.adapter"),
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "mono muted",
                      title: scope.row.adapter ?? "—"
                    }, toDisplayString(scope.row.adapter ?? "—"), 9, _hoisted_11)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.dur"),
                  align: "right",
                  "class-name": "tp-clip"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "mono",
                      title: unref(duration)(scope.row.started_at, scope.row.finished_at)
                    }, toDisplayString(unref(duration)(scope.row.started_at, scope.row.finished_at)), 9, _hoisted_12)
                  ]),
                  _: 1
                }, 8, ["label"])
              ]),
              _: 1
            }, 8, ["data"])
          ])
        ]),
        createVNode(TaskDrawer)
      ]);
    };
  }
});
const TasksView = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-acb0a256"]]);
export {
  TasksView as default
};
