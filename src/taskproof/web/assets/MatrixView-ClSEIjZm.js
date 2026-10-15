import { d as defineComponent, u as useI18n, o as openBlock, c as createElementBlock, w as withKeys, a as withModifiers, b as createBaseVNode, e as createVNode, t as toDisplayString, f as unref, g as createCommentVNode, n as normalizeClass, h as computed, _ as _export_sfc, i as useBoardStore, j as useSettingsStore, k as watch, l as withCtx, m as normalizeStyle, F as Fragment, r as renderList, p as resolveComponent, q as boardQuery, s as useRoute, v as useRouter, H as HIDE_KEY, x as createBlock, R as RANGES, y as createTextVNode, z as columnLabelKey, I as ICONS, A as mergeProps, B as toHandlers, C as owningProject, D as parseBoardFilter, E as visibleProjects, G as visibleColumns, J as gridTracks, K as COLUMNS, L as capChipLabel, M as capMenuFor, N as hiddenTally, O as canGrowBudget, P as groupColumns, Q as filterBoard, S as DEFAULT_CAPS, T as columnWindow } from "./index-Cd1EoUu-.js";
import { S as StatusMark, d as duration, T as TaskDrawer } from "./TaskDrawer-COqi93G5.js";
function acceptancePassed(task) {
  return task.status === "blocked" && task.verify_exit === 0;
}
function laneLabel(task) {
  return task.project;
}
const _hoisted_1$1 = ["data-status", "aria-expanded"];
const _hoisted_2$1 = { class: "line-1" };
const _hoisted_3$1 = { class: "cid" };
const _hoisted_4$1 = { class: "tail" };
const _hoisted_5$1 = {
  key: 0,
  class: "stamp good"
};
const _hoisted_6$1 = { class: "line-2" };
const _hoisted_7$1 = { class: "meta" };
const _hoisted_8$1 = ["title"];
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "TaskCard",
  props: {
    task: {},
    expanded: { type: Boolean }
  },
  emits: ["open"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const { t } = useI18n();
    const stamp = computed(() => {
      const exit = props.task.verify_exit;
      if (exit == null) return null;
      return { text: exit === 0 ? "✓ 0" : `✗ ${exit}`, cls: exit === 0 ? "good" : "bad" };
    });
    const passBadge = computed(() => acceptancePassed(props.task));
    const lane = computed(() => laneLabel(props.task));
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("div", {
        class: "tp-card",
        role: "button",
        tabindex: "0",
        "data-status": __props.task.status,
        "aria-expanded": __props.expanded ? "true" : "false",
        onClick: _cache[0] || (_cache[0] = ($event) => emit("open", __props.task.id)),
        onKeydown: [
          _cache[1] || (_cache[1] = withKeys(withModifiers(($event) => emit("open", __props.task.id), ["prevent"]), ["enter"])),
          _cache[2] || (_cache[2] = withKeys(withModifiers(($event) => emit("open", __props.task.id), ["prevent"]), ["space"]))
        ]
      }, [
        createBaseVNode("span", _hoisted_2$1, [
          createVNode(StatusMark, {
            status: __props.task.status
          }, null, 8, ["status"]),
          createBaseVNode("span", _hoisted_3$1, toDisplayString(__props.task.id), 1),
          createBaseVNode("span", _hoisted_4$1, [
            passBadge.value ? (openBlock(), createElementBlock("span", _hoisted_5$1, toDisplayString(unref(t)("card.acceptancePassed")), 1)) : createCommentVNode("", true),
            stamp.value ? (openBlock(), createElementBlock("span", {
              key: 1,
              class: normalizeClass(["stamp", stamp.value.cls])
            }, toDisplayString(stamp.value.text), 3)) : createCommentVNode("", true),
            _cache[3] || (_cache[3] = createBaseVNode("span", { class: "chev" }, "▸", -1))
          ])
        ]),
        createBaseVNode("span", _hoisted_6$1, toDisplayString(__props.task.brief), 1),
        createBaseVNode("span", _hoisted_7$1, [
          createBaseVNode("span", null, toDisplayString(__props.task.adapter ?? "—"), 1),
          createBaseVNode("span", null, toDisplayString(unref(t)("card.attempt")) + " " + toDisplayString(__props.task.attempt ?? 0), 1),
          createBaseVNode("span", null, toDisplayString(unref(duration)(__props.task.started_at, __props.task.finished_at)), 1),
          createBaseVNode("span", null, toDisplayString(unref(t)("card.files")) + " " + toDisplayString(__props.task.files_changed_live ?? __props.task.files_changed ?? 0), 1),
          createBaseVNode("span", {
            class: "lane",
            title: unref(t)("card.lane")
          }, toDisplayString(lane.value), 9, _hoisted_8$1)
        ])
      ], 40, _hoisted_1$1);
    };
  }
});
const TaskCard = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-695467c5"]]);
const _hoisted_1 = { class: "matrix-view" };
const _hoisted_2 = { class: "boardbar" };
const _hoisted_3 = { class: "fld" };
const _hoisted_4 = { class: "sel-head" };
const _hoisted_5 = ["disabled"];
const _hoisted_6 = ["disabled"];
const _hoisted_7 = ["title"];
const _hoisted_8 = { class: "fld" };
const _hoisted_9 = { class: "rest" };
const _hoisted_10 = ["title"];
const _hoisted_11 = {
  key: 1,
  class: "cap"
};
const _hoisted_12 = {
  key: 1,
  class: "cap-reached"
};
const _hoisted_13 = { class: "matrix" };
const _hoisted_14 = { class: "hd corner" };
const _hoisted_15 = ["data-status"];
const _hoisted_16 = { class: "lb" };
const _hoisted_17 = { class: "rt" };
const _hoisted_18 = ["title", "aria-label", "onClick"];
const _hoisted_19 = ["innerHTML"];
const _hoisted_20 = { class: "hdctl" };
const _hoisted_21 = ["data-col", "title"];
const _hoisted_22 = { class: "cap-chip-label" };
const _hoisted_23 = ["innerHTML"];
const _hoisted_24 = { class: "cap-option-label" };
const _hoisted_25 = {
  key: 0,
  class: "cap-check",
  "aria-hidden": "true"
};
const _hoisted_26 = { class: "lane" };
const _hoisted_27 = ["title"];
const _hoisted_28 = { class: "pth" };
const _hoisted_29 = { class: "tally" };
const _hoisted_30 = { key: 0 };
const _hoisted_31 = {
  key: 1,
  class: "bad"
};
const _hoisted_32 = {
  key: 0,
  class: "dash"
};
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "MatrixView",
  setup(__props) {
    const store = useBoardStore();
    const settings = useSettingsStore();
    const route = useRoute();
    const router = useRouter();
    const { t } = useI18n();
    const filter = computed(() => parseBoardFilter(route.query));
    const projects = computed(() => visibleProjects(store.projectGroups, filter.value));
    const lanes = computed(() => visibleColumns(filter.value));
    const gridStyle = computed(() => ({ gridTemplateColumns: gridTracks(lanes.value.length) }));
    const allProjectIds = computed(() => store.projectGroups.map((group) => group.id));
    const selectedProjects = computed(() => filter.value.projects ?? allProjectIds.value);
    const columns = computed(
      () => groupColumns(filterBoard(store.tasks, filter.value, Date.now(), store.laneProject))
    );
    function capFor(key) {
      return settings.settings.columnCaps[key] ?? DEFAULT_CAPS[key] ?? 0;
    }
    const windows = computed(() => {
      const out = {};
      for (const column of COLUMNS) {
        out[column.key] = columnWindow(columns.value[column.key] ?? [], capFor(column.key));
      }
      return out;
    });
    const capChips = computed(() => {
      const out = {};
      for (const column of COLUMNS) {
        out[column.key] = capChipLabel(
          windows.value[column.key],
          capFor(column.key)
        );
      }
      return out;
    });
    const capMenus = computed(() => {
      const out = {};
      for (const column of COLUMNS) {
        out[column.key] = capMenuFor(capFor(column.key));
      }
      return out;
    });
    const hidden = computed(() => hiddenTally(filter.value, columns.value));
    const canGrow = computed(() => canGrowBudget(store.fetchBudget));
    const shown = computed(() => {
      const out = { ...columns.value };
      for (const column of COLUMNS) out[column.key] = windows.value[column.key].visible;
      return out;
    });
    function tasksIn(projectId, columnKey) {
      return (shown.value[columnKey] ?? []).filter(
        (task) => owningProject(task, store.laneProject) === projectId
      );
    }
    function laneCount(group) {
      return group.taskgroups.length;
    }
    function groupTasks(group) {
      return Object.values(group.summary).reduce((sum, n) => sum + (n || 0), 0);
    }
    function groupFlying(group) {
      return (group.summary.running ?? 0) + (group.summary.verifying ?? 0);
    }
    function groupFailed(group) {
      return (group.summary.failed ?? 0) + (group.summary.timeout ?? 0);
    }
    function aliasHint(group) {
      return group.aliases.join(", ");
    }
    function onCapCommand(key, command) {
      if (typeof command === "number") settings.setColumnCap(key, command);
    }
    function isExpanded(id) {
      return route.params.taskId === id;
    }
    function openTask(id) {
      void router.push({ name: "matrix", params: { taskId: id }, query: route.query });
    }
    const BOARD_KEYS = /* @__PURE__ */ new Set(["range", "projects", "project", HIDE_KEY]);
    function applyFilter(patch) {
      const next = { ...filter.value, ...patch };
      const produced = Object.fromEntries(new URLSearchParams(boardQuery(next)));
      const query = {};
      for (const [key, value] of Object.entries(route.query)) {
        if (!BOARD_KEYS.has(key) && value !== void 0) query[key] = value;
      }
      Object.assign(query, produced);
      void router.push({ query });
    }
    function onRange(value) {
      applyFilter({ range: value });
    }
    function hideLane(key) {
      applyFilter({ hidden: [...filter.value.hidden, key] });
    }
    function showAllLanes() {
      applyFilter({ hidden: [] });
    }
    function onProjects(value) {
      const all = allProjectIds.value;
      const isAll = value.length === all.length && all.every((id) => value.includes(id));
      applyFilter({ projects: isAll ? null : [...value] });
    }
    const allProjectsSelected = computed(() => filter.value.projects === null);
    const noProjectsSelected = computed(
      () => filter.value.projects !== null && filter.value.projects.length === 0
    );
    function selectAllProjects() {
      applyFilter({ projects: null });
    }
    function clearProjects() {
      applyFilter({ projects: [] });
    }
    watch(filter, (next) => store.setRange(next.range), { immediate: true });
    return (_ctx, _cache) => {
      const _component_el_option = resolveComponent("el-option");
      const _component_el_select = resolveComponent("el-select");
      const _component_el_dropdown_item = resolveComponent("el-dropdown-item");
      const _component_el_dropdown_menu = resolveComponent("el-dropdown-menu");
      const _component_el_dropdown = resolveComponent("el-dropdown");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createBaseVNode("div", _hoisted_2, [
          createBaseVNode("label", _hoisted_3, [
            createBaseVNode("span", null, toDisplayString(unref(t)("board.project")), 1),
            createVNode(_component_el_select, {
              class: "sel sel-projects",
              "popper-class": "sel-projects-popper",
              size: "small",
              multiple: "",
              filterable: "",
              "collapse-tags": "",
              "collapse-tags-tooltip": "",
              "model-value": selectedProjects.value,
              onChange: onProjects
            }, {
              header: withCtx(() => [
                createBaseVNode("div", _hoisted_4, [
                  createBaseVNode("button", {
                    type: "button",
                    disabled: allProjectsSelected.value,
                    onClick: withModifiers(selectAllProjects, ["stop", "prevent"])
                  }, toDisplayString(unref(t)("rail.all")), 9, _hoisted_5),
                  createBaseVNode("button", {
                    type: "button",
                    disabled: noProjectsSelected.value,
                    onClick: withModifiers(clearProjects, ["stop", "prevent"])
                  }, toDisplayString(unref(t)("rail.none")), 9, _hoisted_6)
                ])
              ]),
              default: withCtx(() => [
                (openBlock(true), createElementBlock(Fragment, null, renderList(unref(store).projectGroups, (group) => {
                  return openBlock(), createBlock(_component_el_option, {
                    key: group.id,
                    value: group.id,
                    label: group.id
                  }, {
                    default: withCtx(() => [
                      createBaseVNode("span", {
                        title: aliasHint(group) || void 0
                      }, toDisplayString(group.id), 9, _hoisted_7)
                    ]),
                    _: 2
                  }, 1032, ["value", "label"]);
                }), 128))
              ]),
              _: 1
            }, 8, ["model-value"])
          ]),
          createBaseVNode("label", _hoisted_8, [
            createBaseVNode("span", null, toDisplayString(unref(t)("board.range")), 1),
            createVNode(_component_el_select, {
              class: "sel",
              size: "small",
              "model-value": filter.value.range,
              onChange: onRange
            }, {
              default: withCtx(() => [
                (openBlock(true), createElementBlock(Fragment, null, renderList(unref(RANGES), (r) => {
                  return openBlock(), createBlock(_component_el_option, {
                    key: r,
                    value: r,
                    label: unref(t)(`board.ranges.${r}`)
                  }, null, 8, ["value", "label"]);
                }), 128))
              ]),
              _: 1
            }, 8, ["model-value"])
          ]),
          createBaseVNode("div", _hoisted_9, [
            hidden.value.count > 0 ? (openBlock(), createElementBlock("button", {
              key: 0,
              type: "button",
              class: "hidden-lanes",
              title: unref(t)("board.showAllLanes"),
              onClick: showAllLanes
            }, toDisplayString(unref(t)("board.hiddenLanes", { n: hidden.value.count, m: hidden.value.cards })), 9, _hoisted_10)) : createCommentVNode("", true),
            unref(store).capped ? (openBlock(), createElementBlock("div", _hoisted_11, [
              createBaseVNode("span", null, toDisplayString(unref(t)("board.capped", { n: unref(store).tasks.length })), 1),
              canGrow.value ? (openBlock(), createElementBlock("button", {
                key: 0,
                type: "button",
                class: "grow",
                onClick: _cache[0] || (_cache[0] = ($event) => unref(store).growBudget())
              }, toDisplayString(unref(t)("board.continue")), 1)) : (openBlock(), createElementBlock("span", _hoisted_12, toDisplayString(unref(t)("board.capReached")), 1))
            ])) : createCommentVNode("", true)
          ])
        ]),
        createBaseVNode("div", _hoisted_13, [
          createBaseVNode("div", {
            class: "grid",
            style: normalizeStyle(gridStyle.value)
          }, [
            createBaseVNode("div", _hoisted_14, toDisplayString(unref(t)("rail.title")), 1),
            (openBlock(true), createElementBlock(Fragment, null, renderList(lanes.value, (column, index) => {
              return openBlock(), createElementBlock("div", {
                key: column.key,
                class: normalizeClass(["hd", { zcol: index % 2 === 1 }]),
                "data-status": column.key
              }, [
                createBaseVNode("span", _hoisted_16, [
                  createVNode(StatusMark, {
                    status: column.key,
                    shape: "dot"
                  }, null, 8, ["status"]),
                  createTextVNode(" " + toDisplayString(unref(t)(unref(columnLabelKey)(column.key))), 1)
                ]),
                createBaseVNode("span", _hoisted_17, [
                  createBaseVNode("button", {
                    type: "button",
                    class: "lane-hide",
                    title: unref(t)("board.hideLane", { name: unref(t)(unref(columnLabelKey)(column.key)) }),
                    "aria-label": unref(t)("board.hideLane", { name: unref(t)(unref(columnLabelKey)(column.key)) }),
                    onClick: ($event) => hideLane(column.key)
                  }, [
                    createBaseVNode("span", {
                      innerHTML: unref(ICONS).eyeOff
                    }, null, 8, _hoisted_19)
                  ], 8, _hoisted_18)
                ]),
                createBaseVNode("div", _hoisted_20, [
                  createVNode(_component_el_dropdown, {
                    class: "cap-dd",
                    trigger: "click",
                    placement: "bottom-end",
                    "popper-class": "cap-menu-popper",
                    teleported: true,
                    onCommand: (value) => onCapCommand(column.key, value)
                  }, {
                    dropdown: withCtx(() => [
                      createVNode(_component_el_dropdown_menu, null, {
                        default: withCtx(() => [
                          createVNode(_component_el_dropdown_item, {
                            disabled: "",
                            class: "cap-menu-title"
                          }, {
                            default: withCtx(() => [
                              createTextVNode(toDisplayString(unref(t)("board.capMenu.title")), 1)
                            ]),
                            _: 1
                          }),
                          (openBlock(true), createElementBlock(Fragment, null, renderList(capMenus.value[column.key].options, (option) => {
                            return openBlock(), createBlock(_component_el_dropdown_item, {
                              key: option.value,
                              command: option.value
                            }, {
                              default: withCtx(() => [
                                createBaseVNode("span", _hoisted_24, toDisplayString(unref(t)(option.label.key, option.label.params)), 1),
                                option.checked ? (openBlock(), createElementBlock("span", _hoisted_25, "✓")) : createCommentVNode("", true)
                              ]),
                              _: 2
                            }, 1032, ["command"]);
                          }), 128))
                        ]),
                        _: 2
                      }, 1024)
                    ]),
                    default: withCtx(() => [
                      createBaseVNode("button", {
                        type: "button",
                        class: "cap-chip",
                        "data-col": column.key,
                        title: unref(t)("board.capMenu.title"),
                        onClick: _cache[1] || (_cache[1] = withModifiers(() => {
                        }, ["stop"])),
                        onDblclick: _cache[2] || (_cache[2] = withModifiers(() => {
                        }, ["stop"]))
                      }, [
                        createBaseVNode("span", _hoisted_22, toDisplayString(unref(t)(capChips.value[column.key].key, capChips.value[column.key].params)), 1),
                        createBaseVNode("span", {
                          class: "cap-caret",
                          "aria-hidden": "true",
                          innerHTML: unref(ICONS).caret
                        }, null, 8, _hoisted_23)
                      ], 40, _hoisted_21)
                    ]),
                    _: 2
                  }, 1032, ["onCommand"])
                ])
              ], 10, _hoisted_15);
            }), 128)),
            (openBlock(true), createElementBlock(Fragment, null, renderList(projects.value, (group) => {
              return openBlock(), createElementBlock(Fragment, {
                key: group.id
              }, [
                createBaseVNode("div", _hoisted_26, [
                  createBaseVNode("div", {
                    class: "name",
                    title: aliasHint(group) || void 0
                  }, toDisplayString(group.id), 9, _hoisted_27),
                  createBaseVNode("div", _hoisted_28, toDisplayString(group.path), 1),
                  createBaseVNode("div", _hoisted_29, [
                    createBaseVNode("span", null, toDisplayString(laneCount(group)) + " " + toDisplayString(unref(t)("rail.lanes")), 1),
                    createBaseVNode("span", null, toDisplayString(groupTasks(group)) + " " + toDisplayString(unref(t)("rail.tasks")), 1),
                    groupFlying(group) ? (openBlock(), createElementBlock("span", _hoisted_30, toDisplayString(groupFlying(group)) + " " + toDisplayString(unref(t)("tally.flying")), 1)) : createCommentVNode("", true),
                    groupFailed(group) ? (openBlock(), createElementBlock("span", _hoisted_31, toDisplayString(groupFailed(group)) + " " + toDisplayString(unref(t)("tally.failed")), 1)) : createCommentVNode("", true)
                  ])
                ]),
                (openBlock(true), createElementBlock(Fragment, null, renderList(lanes.value, (column, index) => {
                  return openBlock(), createElementBlock("div", {
                    key: column.key,
                    class: normalizeClass(["mcell", { zcol: index % 2 === 1 }])
                  }, [
                    (openBlock(true), createElementBlock(Fragment, null, renderList(tasksIn(group.id, column.key), (task) => {
                      return openBlock(), createBlock(TaskCard, mergeProps({
                        key: task.id,
                        task,
                        expanded: isExpanded(task.id)
                      }, toHandlers({ open: openTask })), null, 16, ["task", "expanded"]);
                    }), 128)),
                    !tasksIn(group.id, column.key).length ? (openBlock(), createElementBlock("div", _hoisted_32, "—")) : createCommentVNode("", true)
                  ], 2);
                }), 128))
              ], 64);
            }), 128))
          ], 4)
        ]),
        createVNode(TaskDrawer)
      ]);
    };
  }
});
const MatrixView = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-6af3c04d"]]);
export {
  MatrixView as default
};
