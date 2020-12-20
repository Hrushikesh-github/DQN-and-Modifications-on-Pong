#!/usr/bin/env python3
import gym
import ptan
import argparse
import random
import torch
import torch.optim as optim
from ignite.engine import Engine

from lib import dqn_model, common

NAME = "02_n_steps"
DEFAULT_N_STEPS = 4


if __name__ == "__main__":
    random.seed(common.SEED)
    torch.manual_seed(common.SEED)
    params = common.HYPERPARAMS['pong']
    parser = argparse.ArgumentParser()
    parser.add_argument("--cuda", default=True, action="store_false",
                        help="Enable cuda")
    parser.add_argument("-n", type=int, default=DEFAULT_N_STEPS,
                        help="Steps to do on Bellman unroll")
    args = parser.parse_args()
    device = torch.device("cuda" if args.cuda else "cpu")

    # Create the environment, wrap it and ensure random seed
    env = gym.make(params.env_name)
    env = ptan.common.wrappers.wrap_dqn(env)
    env.seed(common.SEED)

    # Create the neural network and the target network
    net = dqn_model.DQN(env.observation_space.shape, env.action_space.n).to(device)
    tgt_net = ptan.agent.TargetNet(net)

    # Create the selector and use the epsilon tracker in the common module to keep track of epsilon value
    selector = ptan.actions.EpsilonGreedyActionSelector(epsilon=params.epsilon_start)
    epsilon_tracker = common.EpsilonTracker(selector, params)

    # Create an agent based on the nn and the selector
    agent = ptan.agent.DQNAgent(net, selector, device=device)

    # The ExperienceSourceFirstLast is used to generate trajectories. It returns (state, action, reward, last_state) 
    exp_source = ptan.experience.ExperienceSourceFirstLast(env, agent, gamma=params.gamma, steps_count=args.n) # MODIFICATION FROM dqn_basic
    buffer = ptan.experience.ExperienceReplayBuffer(exp_source, buffer_size=params.replay_size)

    optimizer = optim.Adam(net.parameters(), lr=params.learning_rate)

    def process_batch(engine, batch):
        optimizer.zero_grad()
        loss_v = common.calc_loss_dqn(batch, net, tgt_net.target_model, gamma=params.gamma**args.n, device=device)
        loss_v.backward()
        optimizer.step()
        epsilon_tracker.frame(engine.state.iteration)
        if engine.state.iteration % params.target_net_sync == 0:
            tgt_net.sync()
        return {
            "loss": loss_v.item(),
            "epsilon": selector.epsilon,
        }

    engine = Engine(process_batch)
    common.setup_ignite(engine, params, exp_source, f"{NAME}={args.n}")
    engine.run(common.batch_generator(buffer, params.replay_initial, params.batch_size))
