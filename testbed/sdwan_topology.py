"""Mininet/OVS topology for matched SD-WAN switch-calibration experiments."""

from __future__ import annotations

import argparse
import shlex
from dataclasses import dataclass

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch

from testbed.scenario import Scenario, SwitchEvent, route_flows


@dataclass
class TestbedNetwork:
    net: Mininet
    branch: OVSSwitch
    hub: OVSSwitch
    clients: dict[str, object]
    server: object
    path_ports: dict[str, int]
    class_ports: dict[str, int]
    server_port: int
    scenario: Scenario

    def start(self) -> TestbedNetwork:
        self.net.start()
        self._install_static_neighbors()
        return self

    def stop(self) -> None:
        self.net.stop()

    def install_route(self, event: SwitchEvent, path: str) -> None:
        self._install_route(event, path, operation="add-flow")

    def modify_route(self, event: SwitchEvent, path: str) -> None:
        self._install_route(event, path, operation="mod-flows")

    def clear_class_route(self) -> None:
        self._reset_switch_flows()

    def qdisc_stats(self, path: str) -> str:
        port = self.path_ports[path]
        intf = next(intf for intf, value in self.branch.ports.items() if value == port)
        return self.branch.cmd(f"tc -s qdisc show dev {shlex.quote(intf.name)}")

    def _install_route(self, event: SwitchEvent, path: str, *, operation: str) -> None:
        flows = route_flows(
            self.scenario,
            event,
            path,
            path_port=self.path_ports[path],
            client_port=self.class_ports[
                self.scenario.workloads[event.workload].flow_type
            ],
            server_port=self.server_port,
        )
        for switch_name, fields in flows.values():
            switch = self.branch if switch_name == "s_branch" else self.hub
            command = f"priority=200,{fields['match']},actions={fields['actions']}"
            self._ovs(switch, operation, command)

    def _reset_switch_flows(self) -> None:
        for switch in (self.branch, self.hub):
            self._ovs(switch, "del-flows")
            self._ovs(switch, "add-flow", "priority=0,actions=drop")

    def _install_static_neighbors(self) -> None:
        server_mac = self.server.MAC()
        for client in self.clients.values():
            client.cmd(
                "ip neigh replace "
                f"{self.scenario.server_ip} lladdr {server_mac} dev "
                f"{client.defaultIntf().name}"
            )
            self.server.cmd(
                "ip neigh replace "
                f"{client.IP()} lladdr {client.MAC()} dev "
                f"{self.server.defaultIntf().name}"
            )

    def _ovs(self, switch: OVSSwitch, operation: str, flow: str = "") -> None:
        command = [
            "ovs-ofctl",
            "-O",
            "OpenFlow13",
            operation,
            switch.name,
        ]
        if flow:
            command.append(flow)
        output = switch.cmd(shlex.join(command))
        if output.strip():
            raise RuntimeError(
                f"{switch.name}: ovs-ofctl {operation}: {output.strip()}"
            )


def build_network(scenario: Scenario) -> TestbedNetwork:
    net = Mininet(
        controller=Controller,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
    )
    net.addController("c0", controller=Controller, port=6653)
    branch = net.addSwitch(
        "s_branch",
        cls=OVSSwitch,
        dpid="0000000000000001",
        failMode="secure",
        protocols="OpenFlow13",
    )
    hub = net.addSwitch(
        "s_hub",
        cls=OVSSwitch,
        dpid="0000000000000002",
        failMode="secure",
        protocols="OpenFlow13",
    )

    path_ports: dict[str, int] = {}
    for index, path in enumerate(scenario.paths.values(), start=2):
        link = net.addLink(
            branch,
            hub,
            port1=index,
            port2=index,
            bw=path.capacity_mbps,
            delay=f"{path.one_way_delay_ms}ms",
            jitter=f"{path.jitter_ms}ms",
            loss=path.loss_pct,
            use_tbf=True,
            max_queue_size=scenario.queue_limit_packets,
        )
        path_ports[path.name] = branch.ports[link.intf1]

    clients = {}
    class_ports: dict[str, int] = {}
    next_port = 2 + len(scenario.paths)
    workloads_by_class = {
        workload.flow_type: workload for workload in scenario.workloads.values()
    }
    for host_index, (flow_type, workload) in enumerate(
        workloads_by_class.items(), start=1
    ):
        # Linux interface names are limited to 15 characters; use stable
        # short host names so the generated ``<host>-eth0`` names fit.
        name = f"h{host_index}"
        client = net.addHost(name, ip=f"{workload.client_ip}/24")
        link = net.addLink(client, branch, port2=next_port)
        clients[flow_type] = client
        class_ports[flow_type] = branch.ports[link.intf2]
        next_port += 1

    server = net.addHost("server", ip=f"{scenario.server_ip}/24")
    server_link = net.addLink(server, hub)
    testbed = TestbedNetwork(
        net=net,
        branch=branch,
        hub=hub,
        clients=clients,
        server=server,
        path_ports=path_ports,
        class_ports=class_ports,
        server_port=hub.ports[server_link.intf2],
        scenario=scenario,
    )
    return testbed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--cli", action="store_true")
    args = parser.parse_args()

    from testbed.scenario import load_scenario

    scenario = load_scenario(args.scenario)
    testbed = build_network(scenario).start()
    try:
        for event in scenario.events:
            testbed.install_route(event, event.old_path)
        print("Ping test:")
        print(testbed.net.pingAll())
        testbed.clear_class_route()
        print("Path ports:", testbed.path_ports)
        print("Class ports:", testbed.class_ports)
        if args.cli:
            CLI(testbed.net)
    finally:
        testbed.stop()


if __name__ == "__main__":
    main()
