import { d as defineComponent, i as useBoardStore, u as useI18n, c as createElementBlock, b as createBaseVNode, t as toDisplayString, f as unref, e as createVNode, l as withCtx, h as computed, U as ref, p as resolveComponent, n as normalizeClass, o as openBlock, _ as _export_sfc } from "./index-B-PLdDbR.js";
import { T as TaskDrawer } from "./TaskDrawer-6JoGTH0s.js";
function probeOf(value) {
  return value === "passed" || value === "failed" || value === "none" ? value : null;
}
function newest(a, b) {
  if (a === null) return b;
  if (b === null) return a;
  const ta = Date.parse(a);
  const tb = Date.parse(b);
  if (Number.isNaN(ta)) return b;
  if (Number.isNaN(tb)) return a;
  return tb > ta ? b : a;
}
function totalTasks(summary) {
  return Object.values(summary).reduce((sum, n) => sum + (n || 0), 0);
}
function sumProbe(lanes) {
  let passed = false;
  for (const lane of lanes) {
    if (lane.probe === "failed") return "failed";
    if (lane.probe === "passed") passed = true;
  }
  return passed ? "passed" : "none";
}
function projectRows(groups, details) {
  const byId = /* @__PURE__ */ new Map();
  for (const detail of details) byId.set(detail.id, detail);
  return groups.map((group) => {
    const lanes = group.taskgroups.map((lane) => {
      const detail = byId.get(lane.id);
      return {
        id: lane.id,
        // The roster is the lock's authority; a missing lock means "locks on
        // itself", so it is shown as the lane's own id, never blank.
        group: lane.group || lane.id,
        path: detail?.path ?? lane.path,
        verify: detail?.verify ?? lane.verify ?? null,
        tasks: detail?.tasks ?? 0,
        failed: detail?.failed ?? 0,
        lastActivity: detail?.last_activity ?? null,
        probe: probeOf(detail?.probe ?? lane.probe)
      };
    });
    return {
      id: group.id,
      path: group.path,
      lanes,
      tasks: totalTasks(group.summary),
      inProgress: (group.summary.running ?? 0) + (group.summary.verifying ?? 0),
      failed: group.summary.failed ?? 0,
      lastActivity: lanes.reduce(
        (latest, lane) => newest(latest, lane.lastActivity),
        null
      ),
      probe: sumProbe(lanes)
    };
  });
}
const _hoisted_1 = { class: "projects-view" };
const _hoisted_2 = { class: "panes" };
const _hoisted_3 = { class: "pagehead" };
const _hoisted_4 = { class: "sub" };
const _hoisted_5 = { class: "tp-table" };
const _hoisted_6 = { class: "lanes" };
const _hoisted_7 = { class: "mono" };
const _hoisted_8 = { class: "mono muted" };
const _hoisted_9 = ["title"];
const _hoisted_10 = { class: "mono" };
const _hoisted_11 = { class: "mono muted" };
const _hoisted_12 = { class: "mono" };
const _hoisted_13 = { class: "mono muted" };
const _hoisted_14 = { class: "mono" };
const _hoisted_15 = { class: "mono" };
const _hoisted_16 = { class: "mono" };
const _hoisted_17 = { class: "mono muted" };
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "ProjectsView",
  setup(__props) {
    const board = useBoardStore();
    const { t } = useI18n();
    const rows = computed(() => projectRows(board.projectGroups, board.projects));
    const expanded = ref([]);
    function onExpand(_row, openRows) {
      expanded.value = openRows.map((row) => row.id);
    }
    return (_ctx, _cache) => {
      const _component_el_table_column = resolveComponent("el-table-column");
      const _component_el_table = resolveComponent("el-table");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createBaseVNode("div", _hoisted_2, [
          createBaseVNode("div", _hoisted_3, [
            createBaseVNode("div", null, [
              createBaseVNode("h3", null, toDisplayString(unref(t)("projects.title")), 1),
              createBaseVNode("p", _hoisted_4, toDisplayString(unref(t)("projects.sub")), 1)
            ])
          ]),
          createBaseVNode("div", _hoisted_5, [
            createVNode(_component_el_table, {
              data: rows.value,
              style: { "width": "100%" },
              "row-key": "id",
              "expand-row-keys": expanded.value,
              onExpandChange: onExpand
            }, {
              default: withCtx(() => [
                createVNode(_component_el_table_column, {
                  type: "expand",
                  width: "40"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("div", _hoisted_6, [
                      createVNode(_component_el_table, {
                        data: scope.row.lanes,
                        style: { "width": "100%" }
                      }, {
                        default: withCtx(() => [
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.lane"),
                            "min-width": "150"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", _hoisted_7, toDisplayString(lane.row.id), 1)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.group"),
                            width: "136"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", {
                                class: normalizeClass(["mono", { muted: lane.row.group === "default" }])
                              }, toDisplayString(lane.row.group === "default" ? unref(t)("proj.group.default") : lane.row.group), 3)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.path"),
                            "min-width": "210"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", _hoisted_8, toDisplayString(lane.row.path), 1)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.verify"),
                            "min-width": "240",
                            "class-name": "tp-clip"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", {
                                class: "mono muted",
                                title: lane.row.verify ?? ""
                              }, toDisplayString(lane.row.verify ?? "—"), 9, _hoisted_9)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.tasks"),
                            width: "72",
                            align: "right"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", _hoisted_10, toDisplayString(lane.row.tasks), 1)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.failed"),
                            width: "72",
                            align: "right"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", {
                                class: normalizeClass(["mono", { bad: lane.row.failed > 0 }])
                              }, toDisplayString(lane.row.failed), 3)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.last"),
                            width: "170"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", _hoisted_11, toDisplayString(lane.row.lastActivity ?? "—"), 1)
                            ]),
                            _: 1
                          }, 8, ["label"]),
                          createVNode(_component_el_table_column, {
                            label: unref(t)("projects.col.probe"),
                            width: "112"
                          }, {
                            default: withCtx((lane) => [
                              createBaseVNode("span", {
                                class: normalizeClass(["probe", lane.row.probe ?? "none"])
                              }, toDisplayString(unref(t)("probe." + (lane.row.probe ?? "none"))), 3)
                            ]),
                            _: 1
                          }, 8, ["label"])
                        ]),
                        _: 1
                      }, 8, ["data"])
                    ])
                  ]),
                  _: 1
                }),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.id"),
                  "min-width": "150"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_12, toDisplayString(scope.row.id), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.path"),
                  "min-width": "230"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_13, toDisplayString(scope.row.path), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.lanes"),
                  width: "72",
                  align: "right"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_14, toDisplayString(scope.row.lanes.length), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.tasks"),
                  width: "72",
                  align: "right"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_15, toDisplayString(scope.row.tasks), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.flying"),
                  width: "72",
                  align: "right"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_16, toDisplayString(scope.row.inProgress), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.failed"),
                  width: "72",
                  align: "right"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: normalizeClass(["mono", { bad: scope.row.failed > 0 }])
                    }, toDisplayString(scope.row.failed), 3)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.last"),
                  width: "170"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", _hoisted_17, toDisplayString(scope.row.lastActivity ?? "—"), 1)
                  ]),
                  _: 1
                }, 8, ["label"]),
                createVNode(_component_el_table_column, {
                  label: unref(t)("projects.col.probe"),
                  width: "112"
                }, {
                  default: withCtx((scope) => [
                    createBaseVNode("span", {
                      class: normalizeClass(["probe", scope.row.probe ?? "none"])
                    }, toDisplayString(unref(t)("probe." + (scope.row.probe ?? "none"))), 3)
                  ]),
                  _: 1
                }, 8, ["label"])
              ]),
              _: 1
            }, 8, ["data", "expand-row-keys"])
          ])
        ]),
        createVNode(TaskDrawer)
      ]);
    };
  }
});
const ProjectsView = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-a5cb12d2"]]);
export {
  ProjectsView as default
};
