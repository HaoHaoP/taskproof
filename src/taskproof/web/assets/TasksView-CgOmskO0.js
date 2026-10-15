import { d as defineComponent, i as useBoardStore, u as useI18n, c as createElementBlock, b as createBaseVNode, t as toDisplayString, f as unref, g as createCommentVNode, e as createVNode, l as withCtx, h as computed, p as resolveComponent, v as useRouter, s as useRoute, o as openBlock, _ as _export_sfc } from "./index-Cd1EoUu-.js";
import { T as TaskDrawer, d as duration } from "./TaskDrawer-COqi93G5.js";
const _hoisted_1 = { class: "tasks-view" };
const _hoisted_2 = { class: "panes" };
const _hoisted_3 = { class: "sub" };
const _hoisted_4 = { class: "taken" };
const _hoisted_5 = { class: "tp-table" };
const _hoisted_6 = ["data-status"];
const _hoisted_7 = { class: "mono" };
const _hoisted_8 = { class: "mono muted" };
const _hoisted_9 = { class: "mono muted" };
const _hoisted_10 = { class: "mono" };
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "TasksView",
  setup(__props) {
    const store = useBoardStore();
    const router = useRouter();
    const route = useRoute();
    const { t } = useI18n();
    const rows = computed(() => store.tasks);
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
              style: { "width": "100%" },
              onRowClick: _cache[1] || (_cache[1] = (row) => open(row.id))
            }, {
              default: withCtx(() => [
                createVNode(_component_el_table_column, {
                  label: unref(t)("status.label"),
                  width: "92"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: "sc",
                      "data-status": scope.row.status
                    }, toDisplayString(unref(t)(`status.${scope.row.status}`)), 9, _hoisted_6)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: "id",
                  width: "148"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_7, toDisplayString(scope.row.id), 1)
                  ]),
                  _: 1
                }),
                createVNode(_component_el_table_column, {
                  label: unref(t)("rail.title"),
                  width: "118"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_8, toDisplayString(scope.row.project), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  prop: "brief",
                  label: unref(t)("tasks.col.brief"),
                  "min-width": "300",
                  "class-name": "tp-clip"
                }, null, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.adapter"),
                  width: "126"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_9, toDisplayString(scope.row.adapter ?? "—"), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("tasks.col.dur"),
                  width: "82",
                  align: "right"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_10, toDisplayString(unref(duration)(scope.row.started_at, scope.row.finished_at)), 1)
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
const TasksView = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-5700280e"]]);
export {
  TasksView as default
};
