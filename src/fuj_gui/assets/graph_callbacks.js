/**
 * Clientside callbacks for the PI / MPD rolling graph.
 *
 * Both functions run entirely in the browser — no round-trip to Gunicorn.
 * They are registered in callbacks/graph.py via ClientsideFunction.
 */

window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.graph_callbacks = {

    /**
     * Append one telemetry sample from status-store to graph-store and trim
     * the rolling window to max_points.
     *
     * Inputs:  status_data  — contents of status-store
     *          graph_data   — current graph-store (State)
     *          settings     — graph-settings-store: {max_points, window_s}
     * Output:  updated graph-store
     */
    update_graph_store: function (status_data, graph_data, settings) {
        if (!status_data || !settings) return window.dash_clientside.no_update;

        var pi = status_data.peak_indicators || {};
        var mpd_value = status_data.mpd_value;

        // Skip when there is no real telemetry (system not READY)
        var has_pi = pi && typeof pi === "object" && Object.keys(pi).length > 0;
        if (!has_pi && (mpd_value === null || mpd_value === undefined)) {
            return window.dash_clientside.no_update;
        }

        // Clone to avoid mutating the frozen store reference
        graph_data = graph_data
            ? JSON.parse(JSON.stringify(graph_data))
            : { t: [], pi_xi: [], pi_xq: [], pi_yi: [], pi_yq: [], mpd: [] };

        graph_data.t.push(new Date().toISOString());
        graph_data.pi_xi.push(pi.pi_xi !== undefined ? pi.pi_xi : null);
        graph_data.pi_xq.push(pi.pi_xq !== undefined ? pi.pi_xq : null);
        graph_data.pi_yi.push(pi.pi_yi !== undefined ? pi.pi_yi : null);
        graph_data.pi_yq.push(pi.pi_yq !== undefined ? pi.pi_yq : null);
        graph_data.mpd.push(mpd_value !== undefined ? mpd_value : null);

        var max_points = settings.max_points;
        if (graph_data.t.length > max_points) {
            var trim = graph_data.t.length - max_points;
            Object.keys(graph_data).forEach(function (key) {
                graph_data[key] = graph_data[key].slice(trim);
            });
        }

        return graph_data;
    },

    /**
     * Build and return a Plotly figure dict from graph-store.
     * The X-axis is pinned to [now - window_s, now] so grid lines stay fixed.
     *
     * Inputs:  graph_data — contents of graph-store
     *          settings   — graph-settings-store: {max_points, window_s}
     * Output:  dcc.Graph figure property
     */
    render_graph: function (graph_data, settings) {
        var BG = "#1e1e2e";
        var COLORS = {
            pi_xi: "#00b4d8",
            pi_xq: "#90e0ef",
            pi_yi: "#f77f00",
            pi_yq: "#fcbf49",
            mpd:   "#a8dadc"
        };
        if (!graph_data || !graph_data.t || graph_data.t.length === 0) {
            return window.dash_clientside.no_update;
        }
        if (!settings) return window.dash_clientside.no_update;

        var keys = ["pi_xi", "pi_xq", "pi_yi", "pi_yq", "mpd"];
        var traces = keys.map(function (key) {
            return {
                x:    graph_data.t,
                y:    graph_data[key],
                name: key.toUpperCase(),
                type: "scatter",
                mode: "lines",
                line: { color: COLORS[key], width: 1.5 }
            };
        });

        var now     = new Date();
        var x_end   = now.toISOString();
        var x_start = new Date(now.getTime() - settings.window_s * 1000).toISOString();

        return {
            data: traces,
            layout: {
                title:         { text: "Peak Indicators & MPD", font: { color: "#cdd6f4" } },
                paper_bgcolor: BG,
                plot_bgcolor:  BG,
                font:          { color: "#cdd6f4" },
                xaxis: {
                    type:       "date",
                    range:      [x_start, x_end],
                    tickformat: "%H:%M:%S",
                    gridcolor:  "#313244",
                    tickfont:   { color: "#cdd6f4" }
                },
                yaxis: {
                    title:     "Voltage (V)",
                    range:     [0, 2.2],
                    gridcolor: "#313244",
                    tickfont:  { color: "#cdd6f4" }
                },
                legend:     { font: { color: "#cdd6f4" } },
                margin:     { l: 50, r: 20, t: 40, b: 50 },
                uirevision: "constant"
            }
        };
    }
};
