import networkx as nx
import copy
from tree_recovery import r_tree, get_root, DP_optimal, plot_graph
import math
import itertools
import random

class environment:
    def __init__(self, G, independent_nodes, resources):
        '''
        :param G: networkx graph with utility and demand attribute set for each node
        :param independent_nodes: Initial independent nodes of G
        :param resources: resources per recovery step (used in calculation of maximum rounds)
        '''
        self.G = G
        self.number_of_nodes = G.number_of_nodes()

        # stays constant across episodes so when we reset we do it cleanly
        self.G_constant = copy.deepcopy(G)
        self.independent_nodes = independent_nodes

        self.start_demand = nx.get_node_attributes(self.G_constant, 'demand')

        # state is an indicator matrix for each node in G. 0 -> node is offline
        # initially, every node is except for independent nodes
        self.state = [0 for x in range(self.number_of_nodes)]
        for node in self.independent_nodes:
            self.state[node] = 1

        # max rounds is math.ceil(sum(d) / resources)
        self.round = 1
        self.resources = resources

        self.actions_permutations = list(itertools.permutations(range(self.number_of_nodes), 2))

        # True when state is vector of 1's
        self.done = False

    def random_action(self):
        '''
        @@ TODO: fix the random action for the first action taken in an episode
        Random action that does not saturate and is guaranteed to be adjacent to a functional node

        :return: random action index in self.actions_permutations
        '''
        # get demand values of our graph
        demand = nx.get_node_attributes(self.G_constant, 'demand')

        functional_nodes = []
        for node in self.G:
            for id_node in self.independent_nodes:
                if nx.has_path(self.G, id_node, node) and id_node != node:
                    functional_nodes.append(node)

        # possible nodes must be adjacent to either functional or independent nodes
        adjacent_to = functional_nodes + self.independent_nodes
        adjacent_to = list(set(adjacent_to))

        #print('adjto', adjacent_to)
        possible_recovery = []
        for adj_node in adjacent_to:
            for node in range(self.number_of_nodes):
                if node in self.G_constant.neighbors(adj_node) and node != adj_node and demand[node] > 0:
                    possible_recovery.append(node)

        possible_recovery = list(set(possible_recovery) - set(self.independent_nodes))
        #print(possible_recovery)

        # if we have only a single option to recover, naively choose it
        if len(possible_recovery) == 1:
            random_index_list = list(range(self.number_of_nodes))
            random_index_list.pop(random_index_list.index(possible_recovery[0]))
            random_action_choice = (possible_recovery[0], random.choice(random_index_list))

        # otherwise, we take all our recovery options and take a random two
        else:
            random_action_list = list(itertools.permutations(possible_recovery, 2))
            random_action_choice = random.choice(random_action_list)

        return self.actions_permutations.index(random_action_choice)


    def convert_action(self, action):
        '''
        Given an action a, which is an index into a permutation list of length num_nodesP2, we return
        the action represented as a vector to be applied to our demand dict.

        :param action: index into list of permutations.
        :return: number_of_nodes length vector representing the action to be taken
        '''
        # check for a random action first
        if action == -1:
            action = random.randint(0, len(self.actions_permutations) - 1)

        node_pair = self.actions_permutations[action]

        true_action = [0 for x in range(self.number_of_nodes)]

        # get demand values of our graph
        demand = nx.get_node_attributes(self.G_constant, 'demand')

        # if we have extra resources, put them into the second node's allocation
        if demand[node_pair[0]] < self.resources:
            true_action[node_pair[0]] = demand[node_pair[0]]
            true_action[node_pair[1]] = self.resources - demand[node_pair[0]]

        # otherwise we just apply maximum resources to the first node
        else:
            true_action[node_pair[0]] = self.resources

        return true_action

    def step(self, action, action_is_index=True, debug=False):
        '''
        Applies a partition of resources to the graph G

        :param action: index to a specific |V(G)| len vector, where sum(action) == resources at a time step.
        :param action_is_index: If we wish to test the best config, we only have real action vectors so no need to convert. Usually only have indices
        :param debug: output data for test runs
        :return: state, reward, done
        '''
        # turn index-based permutation into a vector representation
        if action_is_index:
            action = self.convert_action(action)
        if debug:
            print('action', action)

        utils = nx.get_node_attributes(self.G_constant, 'util')
        demand = nx.get_node_attributes(self.G_constant, 'demand')

        # apply resources to demand vector
        demand = [max(demand[x] - action[x], 0) for x in range(len(action))]

        # update state
        self.state = [1 if demand[x] == 0 or self.state[x] == 1 else 0 for x in range(len(action))]

        # G becomes subgraph of functional nodes
        self.G = self.G_constant.subgraph([x if self.state[x] == 1 else None for x in range(len(self.state))])

        # count utility only for nodes which have a path to an independent node
        count_utility = []
        for node in self.G:
            for id_node in self.independent_nodes:
                if nx.has_path(self.G, id_node, node) and id_node != node:
                    count_utility.append(node)

        if debug:
            print('count_utility', count_utility)
        
        # utility at this time step is reward
        reward = sum([utils[x] if x in count_utility else 0 for x in range(len(action))])

        # convert demand back to dict
        demand = dict((i, demand[i]) for i in range(len(demand)))

        # update demand values in our current graph
        nx.set_node_attributes(self.G_constant, name='demand', values=demand)

        # check if we are finished with this episode
        if self.state == [1 for x in self.state]:
            self.done = True

        # check if we have reached round limit, which is ceil(sum(demands of non-independent nodes) / resources per turn)
        independent_node_demand = [self.start_demand[x] for x in self.independent_nodes]

        if self.round >= (math.ceil((sum(self.start_demand.values()) - sum(independent_node_demand))/ self.resources)):
            self.done = True

        self.round += 1

        return self.state, reward, self.done

    def reset(self):
        '''
        Reset our state to starting state, return an initial observation

        :return: initial state, 'False' done boolean
        '''
        self.G = copy.deepcopy(self.G_constant)
        self.state = [0 for x in range(self.number_of_nodes)]
        for node in self.independent_nodes:
            self.state[node] = 1
        
        # reset demands, we don't modify utils
        nx.set_node_attributes(self.G_constant, name='demand', values=self.start_demand)

        # True when state is vector of 1's
        self.done = False
        self.round = 1

        return self.state, self.done


def main():
    # test
    num_nodes = 7
    G = r_tree(num_nodes)
    plot_graph(G, get_root(G), 'environment_debug_graph.png')
    env = environment(G, [get_root(G)], 1)
    while not env.done:
        print(env.step(random.randint(0, 10)))
        print()

    env.reset()
    print('Reset env =========================')
    while not env.done:
        print(env.step(random.randint(0, 10)))
        print()


if __name__ == "__main__":
    # main()
    None