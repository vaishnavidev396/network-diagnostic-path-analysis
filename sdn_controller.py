"""Loop-free Ryu OpenFlow 1.3 controller for the bundled diamond topology.

Uses the fixed port layout created by topology.py. LLDP topology discovery
selects the first available route, and controller-managed source-MAC flows
carry both ARP and UDP traffic without Ethernet flooding.
"""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub
from ryu.lib.packet import packet, ethernet
from ryu.lib.packet import ether_types
from ryu.topology import event
from ryu.topology.api import get_link

H1_MAC = '00:00:00:00:00:01'
H4_MAC = '00:00:00:00:00:02'
# The port numbers below follow the order of addLink() in topology.py.
PORT = {
    1: {0: 1, 2: 2, 3: 3},  # h1, s2, s3
    2: {1: 1, 4: 2},
    3: {1: 1, 4: 2},
    4: {2: 1, 3: 2, 0: 3},  # s2, s3, h4
}
PATHS = ((1, 2, 4), (1, 3, 4))
COOKIE = 0xD1A6


class NetworkDiagnosticController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.active_path = None
        self.worker = hub.spawn(self._watch_topology)
        self.logger.info('Loop-free diagnostic controller started')

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self, ev):
        dp = ev.msg.datapath
        self.datapaths[dp.id] = dp
        p, o = dp.ofproto_parser, dp.ofproto
        # Table miss sends unmatched packets to the controller (not FLOOD).
        dp.send_msg(p.OFPFlowMod(
            datapath=dp, priority=0, match=p.OFPMatch(),
            instructions=[p.OFPInstructionActions(
                o.OFPIT_APPLY_ACTIONS,
                [p.OFPActionOutput(o.OFPP_CONTROLLER, o.OFPCML_NO_BUFFER)])]))
        self.active_path = None

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change(self, ev):
        if ev.state == MAIN_DISPATCHER:
            self.datapaths[ev.datapath.id] = ev.datapath
        elif ev.state == DEAD_DISPATCHER:
            self.datapaths.pop(ev.datapath.id, None)
            self.active_path = None

    def _watch_topology(self):
        while True:
            try:
                self._refresh_route()
            except Exception as exc:
                self.logger.warning('Route refresh failed: %s', exc)
            hub.sleep(1)

    def _refresh_route(self):
        if not all(s in self.datapaths for s in (1, 2, 3, 4)):
            return
        directed = {(l.src.dpid, l.dst.dpid) for l in get_link(self, None)}
        chosen = None
        for path in PATHS:
            if all((a, b) in directed and (b, a) in directed
                   for a, b in zip(path, path[1:])):
                chosen = path
                break
        if chosen == self.active_path:
            return
        self.logger.info('Active path changed: %s -> %s', self.active_path, chosen)
        # Remove only our own flows, leaving LLDP and table-miss rules intact.
        for dp in list(self.datapaths.values()):
            p, o = dp.ofproto_parser, dp.ofproto
            dp.send_msg(p.OFPFlowMod(
                datapath=dp, cookie=COOKIE, cookie_mask=0xFFFFFFFFFFFFFFFF,
                table_id=0, command=o.OFPFC_DELETE,
                out_port=o.OFPP_ANY, out_group=o.OFPG_ANY,
                match=p.OFPMatch()))
        self.active_path = chosen
        if chosen is None:
            return
        full_path = (0,) + chosen + (0,)
        for index in range(1, len(full_path) - 1):
            switch = full_path[index]
            dp = self.datapaths[switch]
            prev_node, next_node = full_path[index - 1], full_path[index + 1]
            self._add_forward(dp, H1_MAC, PORT[switch][prev_node], PORT[switch][next_node])
            self._add_forward(dp, H4_MAC, PORT[switch][next_node], PORT[switch][prev_node])
        # Barrier makes ordering explicit for each datapath.
        for dp in self.datapaths.values():
            dp.send_msg(dp.ofproto_parser.OFPBarrierRequest(dp))

    def _add_forward(self, dp, source_mac, in_port, out_port):
        p, o = dp.ofproto_parser, dp.ofproto
        dp.send_msg(p.OFPFlowMod(
            datapath=dp, cookie=COOKIE, priority=100,
            match=p.OFPMatch(in_port=in_port, eth_src=source_mac),
            instructions=[p.OFPInstructionActions(
                o.OFPIT_APPLY_ACTIONS, [p.OFPActionOutput(out_port)])]))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in(self, ev):
        # No flooding: after topology discovery the proactively installed
        # source-MAC flows carry ARP and IPv4/UDP in both directions.
        msg = ev.msg
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return
        # A packet may arrive during discovery or a route transition.
        # Drop it rather than forwarding around the diamond loop.

    @set_ev_cls(event.EventSwitchEnter)
    @set_ev_cls(event.EventSwitchLeave)
    @set_ev_cls(event.EventLinkAdd)
    @set_ev_cls(event.EventLinkDelete)
    def topology_changed(self, ev):
        # The background watcher checks link discovery every second.
        pass
