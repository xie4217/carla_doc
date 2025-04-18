#!/usr/bin/env python

# Copyright (c) 2020 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""
Script that render multiple sensors in the same pygame window

By default, it renders four cameras, one LiDAR and one Semantic LiDAR.
It can easily be configure for any different number of sensors. 
To do that, check lines 290-308.
"""

# 默认分辨率会花屏，需要修改默认分辨率：--res 1152x648
# 参考：https://blog.csdn.net/qq_45892641/article/details/131635147


import glob
import os
import sys

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla
import argparse
import random
import time
import numpy as np


try:
    import pygame
    from pygame.locals import K_ESCAPE
    from pygame.locals import K_q
except ImportError:
    raise RuntimeError('cannot import pygame, make sure pygame package is installed')


# 计时器
class CustomTimer:
    # 使用本机时间作为计时器，如果报错则改用浮点秒数计时
    def __init__(self):
        try:
            self.timer = time.perf_counter  # 返回处理器的性能计数器的值，具有最高分辨率，用于测量短持续时间。
        except AttributeError:
            self.timer = time.time  # 返回的是经过调整的时间戳，而time.perf_counter()的返回值不体现”时间”,只记录处理器经过的”时间段”

    # 返回计时器
    def time(self):
        return self.timer()


# 显示控制器
class DisplayManager:
    # 根据输入窗口大小初始化现实控制器并启用硬件加速、双缓冲
    def __init__(self, grid_size, window_size):
        pygame.init()
        pygame.font.init()
        self.display = pygame.display.set_mode(window_size, pygame.HWSURFACE | pygame.DOUBLEBUF)

        self.grid_size = grid_size
        self.window_size = window_size
        self.sensor_list = []

    # 返回整个窗口大小
    def get_window_size(self):
        return [int(self.window_size[0]), int(self.window_size[1])]

    # 返回单个监视窗的大小
    def get_display_size(self):
        return [int(self.window_size[0]/self.grid_size[1]), int(self.window_size[1]/self.grid_size[0])]

    # 返回单个监视窗的位置
    def get_display_offset(self, gridPos):
        dis_size = self.get_display_size()
        return [int(gridPos[1] * dis_size[0]), int(gridPos[0] * dis_size[1])]

    # 添加传感器
    def add_sensor(self, sensor):
        self.sensor_list.append(sensor)

    # 获取传感器列表
    def get_sensor_list(self):
        return self.sensor_list

    # 渲染画面并将画面输出
    def render(self):
        if not self.render_enabled():
            return

        for s in self.sensor_list:
            s.render()

        pygame.display.flip()  # 刷新游戏窗口的显示，对所有缓冲区进行更新。而pygame.display.update()只会更新参数中指定的部分屏幕缓冲区

    # 销毁传感器
    def destroy(self):
        for s in self.sensor_list:
            s.destroy()

    # 渲染开关
    def render_enabled(self):
        return self.display != None


# 传感器控制器
class SensorManager:
    # 初始化传感器，计时器等
    def __init__(self, world, display_man, sensor_type, transform, attached, sensor_options, display_pos):
        self.surface = None
        self.world = world
        self.display_man = display_man
        self.display_pos = display_pos
        self.sensor = self.init_sensor(sensor_type, transform, attached, sensor_options)
        self.sensor_options = sensor_options
        self.timer = CustomTimer()

        self.time_processing = 0.0
        self.tics_processing = 0

        self.display_man.add_sensor(self)

    # 初始化传感器方法
    def init_sensor(self, sensor_type, transform, attached, sensor_options):
        # 当输入传感器类型为RGBCamera时
        if sensor_type == 'RGBCamera':
            camera_bp = self.world.get_blueprint_library().find('sensor.camera.rgb')
            disp_size = self.display_man.get_display_size()
            camera_bp.set_attribute('image_size_x', str(disp_size[0]))
            camera_bp.set_attribute('image_size_y', str(disp_size[1]))

            for key in sensor_options:
                camera_bp.set_attribute(key, sensor_options[key])

            camera = self.world.spawn_actor(camera_bp, transform, attach_to=attached)
            camera.listen(self.save_rgb_image)

            return camera

        # 当输入传感器类型为LiDAR时
        elif sensor_type == 'LiDAR':
            lidar_bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast')
            lidar_bp.set_attribute('range', '100')
            lidar_bp.set_attribute('dropoff_general_rate', lidar_bp.get_attribute('dropoff_general_rate').recommended_values[0])
            lidar_bp.set_attribute('dropoff_intensity_limit', lidar_bp.get_attribute('dropoff_intensity_limit').recommended_values[0])
            lidar_bp.set_attribute('dropoff_zero_intensity', lidar_bp.get_attribute('dropoff_zero_intensity').recommended_values[0])

            for key in sensor_options:
                lidar_bp.set_attribute(key, sensor_options[key])

            lidar = self.world.spawn_actor(lidar_bp, transform, attach_to=attached)

            lidar.listen(self.save_lidar_image)

            return lidar

        # 当输入传感器类型为SemanticLiDAR时
        elif sensor_type == 'SemanticLiDAR':
            lidar_bp = self.world.get_blueprint_library().find('sensor.lidar.ray_cast_semantic')
            lidar_bp.set_attribute('range', '100')

            for key in sensor_options:
                lidar_bp.set_attribute(key, sensor_options[key])

            lidar = self.world.spawn_actor(lidar_bp, transform, attach_to=attached)

            lidar.listen(self.save_semanticlidar_image)

            return lidar

        # 当输入传感器类型为Radar时
        elif sensor_type == "Radar":
            radar_bp = self.world.get_blueprint_library().find('sensor.other.radar')
            for key in sensor_options:
                radar_bp.set_attribute(key, sensor_options[key])

            radar = self.world.spawn_actor(radar_bp, transform, attach_to=attached)
            radar.listen(self.save_radar_image)

            return radar

        # 当输入传感器类型为DepthCamera时
        elif sensor_type == "DepthCamera":
            depth_camera_bp = self.world.get_blueprint_library().find('sensor.camera.depth')
            for key in sensor_options:
                depth_camera_bp.set_attribute(key, sensor_options[key])

            depth_camera = self.world.spawn_actor(depth_camera_bp, transform, attach_to=attached)
            depth_camera.listen(self.save_depth_image)

            return depth_camera

        # 当输入传感器类型为InstanceSegmentationCamera时
        elif sensor_type == "InstanceSegmentationCamera":
            instance_segmentation_camera_bp = self.world.get_blueprint_library().find(
                'sensor.camera.instance_segmentation')
            for key in sensor_options:
                instance_segmentation_camera_bp.set_attribute(key, sensor_options[key])

            instance_segmentation_camera = self.world.spawn_actor(instance_segmentation_camera_bp, transform,
                                                                  attach_to=attached)
            instance_segmentation_camera.listen(self.save_instance_segmentation_image)

            return instance_segmentation_camera

        else:
            return None

    # 获取传感器
    def get_sensor(self):
        return self.sensor

    # 转化rgb图像，渲染并更新时间
    def save_rgb_image(self, image):
        t_start = self.timer.time()

        image.convert(carla.ColorConverter.Raw)
        array = np.frombuffer(image.raw_data, dtype=np.dtype("uint8"))
        array = np.reshape(array, (image.height, image.width, 4))
        array = array[:, :, :3]
        array = array[:, :, ::-1]

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))

        t_end = self.timer.time()
        self.time_processing += (t_end-t_start)
        self.tics_processing += 1

    # 转化深度图像，渲染并更新时间
    def save_depth_image(self, image):
        t_start = self.timer.time()

        image.convert(carla.ColorConverter.LogarithmicDepth)
        array = np.frombuffer(image.raw_data, dtype=np.dtype("uint8"))
        array = np.reshape(array, (image.height, image.width, 4))
        array = array[:, :, :3]
        array = array[:, :, ::-1]

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))

        t_end = self.timer.time()
        self.time_processing += (t_end - t_start)
        self.tics_processing += 1

    def save_lidar_image(self, image):
        t_start = self.timer.time()

        disp_size = self.display_man.get_display_size()
        lidar_range = 2.0*float(self.sensor_options['range'])

        points = np.frombuffer(image.raw_data, dtype=np.dtype('f4'))
        points = np.reshape(points, (int(points.shape[0] / 4), 4))
        lidar_data = np.array(points[:, :2])
        lidar_data *= min(disp_size) / lidar_range
        lidar_data += (0.5 * disp_size[0], 0.5 * disp_size[1])
        lidar_data = np.fabs(lidar_data)  # pylint: disable=E1111
        lidar_data = lidar_data.astype(np.int32)
        lidar_data = np.reshape(lidar_data, (-1, 2))
        lidar_img_size = (disp_size[0], disp_size[1], 3)
        lidar_img = np.zeros((lidar_img_size), dtype=np.uint8)

        lidar_img[tuple(lidar_data.T)] = (255, 255, 255)

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(lidar_img)

        t_end = self.timer.time()
        self.time_processing += (t_end-t_start)
        self.tics_processing += 1

    # 转化instance_segmentation图像，渲染并更新时间
    def save_instance_segmentation_image(self, image):
        t_start = self.timer.time()

        image.convert(carla.ColorConverter.Raw)
        array = np.frombuffer(image.raw_data, dtype=np.dtype("uint8"))
        array = np.reshape(array, (image.height, image.width, 4))
        array = array[:, :, :3]
        array = array[:, :, ::-1]

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(array.swapaxes(0, 1))

        t_end = self.timer.time()
        self.time_processing += (t_end - t_start)
        self.tics_processing += 1

    # 转化lidar数据，渲染并更新时间
    def save_lidar_image(self, image):
        t_start = self.timer.time()

        disp_size = self.display_man.get_display_size()
        lidar_range = 2.0 * float(self.sensor_options['range'])

        points = np.frombuffer(image.raw_data, dtype=np.dtype('f4'))
        points = np.reshape(points, (int(points.shape[0] / 4), 4))
        lidar_data = np.array(points[:, :2])
        lidar_data *= min(disp_size) / lidar_range
        lidar_data += (0.5 * disp_size[0], 0.5 * disp_size[1])
        lidar_data = np.fabs(lidar_data)  # pylint: disable=E1111
        lidar_data = lidar_data.astype(np.int32)
        lidar_data = np.reshape(lidar_data, (-1, 2))
        lidar_img_size = (disp_size[0], disp_size[1], 3)
        lidar_img = np.zeros((lidar_img_size), dtype=np.uint8)

        lidar_img[tuple(lidar_data.T)] = (255, 255, 255)

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(lidar_img)

        t_end = self.timer.time()
        self.time_processing += (t_end - t_start)
        self.tics_processing += 1

    # 转化semantic_segmentation图像，渲染并更新时间
    def save_semanticlidar_image(self, image):
        t_start = self.timer.time()

        disp_size = self.display_man.get_display_size()
        lidar_range = 2.0*float(self.sensor_options['range'])

        points = np.frombuffer(image.raw_data, dtype=np.dtype('f4'))
        points = np.reshape(points, (int(points.shape[0] / 6), 6))
        lidar_data = np.array(points[:, :2])
        lidar_data *= min(disp_size) / lidar_range
        lidar_data += (0.5 * disp_size[0], 0.5 * disp_size[1])
        lidar_data = np.fabs(lidar_data)  # pylint: disable=E1111
        lidar_data = lidar_data.astype(np.int32)
        lidar_data = np.reshape(lidar_data, (-1, 2))
        lidar_img_size = (disp_size[0], disp_size[1], 3)
        lidar_img = np.zeros((lidar_img_size), dtype=np.uint8)

        lidar_img[tuple(lidar_data.T)] = (255, 255, 255)

        if self.display_man.render_enabled():
            self.surface = pygame.surfarray.make_surface(lidar_img)

        t_end = self.timer.time()
        self.time_processing += (t_end-t_start)
        self.tics_processing += 1

    # 转换radar数据并更新时间
    def save_radar_image(self, radar_data):
        t_start = self.timer.time()
        points = np.frombuffer(radar_data.raw_data, dtype=np.dtype('f4'))
        points = np.reshape(points, (len(radar_data), 4))

        t_end = self.timer.time()
        self.time_processing += (t_end-t_start)
        self.tics_processing += 1

    # 渲染屏幕输出
    def render(self):
        if self.surface is not None:
            offset = self.display_man.get_display_offset(self.display_pos)
            self.display_man.display.blit(self.surface, offset)

    # 摧毁传感器
    def destroy(self):
        self.sensor.destroy()


def run_simulation(args, client):
    """This function performed one test run using the args parameters
    and connecting to the carla client passed.
    """

    display_manager = None
    vehicle = None
    vehicle_list = []
    timer = CustomTimer()

    try:

        # Getting the world and
        world = client.get_world()
        original_settings = world.get_settings()

        if args.sync:
            traffic_manager = client.get_trafficmanager(8000)
            settings = world.get_settings()
            traffic_manager.set_synchronous_mode(True)
            settings.synchronous_mode = True
            settings.fixed_delta_seconds = 0.05
            world.apply_settings(settings)

        # Instanciating the vehicle to which we attached the sensors
        bp = world.get_blueprint_library().filter('charger_2020')[0]
        vehicle = world.spawn_actor(bp, random.choice(world.get_map().get_spawn_points()))
        vehicle_list.append(vehicle)
        vehicle.set_autopilot(True)

        # Display Manager organize all the sensors an its display in a window
        # If can easily configure the grid and the total window size
        display_manager = DisplayManager(grid_size=[2, 3], window_size=[args.width, args.height])

        # 传感器管理器负责根据我们输入的属性去初始化传感器并且将最终的显示输出的位置进行管理，这里初始化了
        # RGBCamera，DepthCamera，SemanticSegmentationCamera，InstanceSegmentationCamera
        # LiDAR以及SemanticLiDAR共6个传感器
        # SensorManager(world, display_manager, 'DepthCamera',
        #               carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
        #               vehicle, {'fov': '90'}, display_pos=[0, 0])  # 第一排第一个为深度相机
        # SensorManager(world, display_manager, 'RGBCamera',
        #               carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
        #               vehicle, {'fov': '90'}, display_pos=[0, 1])  # 第一排第二个为RGB相机
        # SensorManager(world, display_manager, 'SemanticSegmentationCamera',
        #               carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
        #               vehicle, {'fov': '90'}, display_pos=[0, 2])  # 第一排第三个为语义分割相机

        # Then, SensorManager can be used to spawn RGBCamera, LiDARs and SemanticLiDARs as needed
        # and assign each of them to a grid position, 
        SensorManager(world, display_manager, 'RGBCamera', carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=-90)),
                      vehicle, {}, display_pos=[0, 0])
        SensorManager(world, display_manager, 'RGBCamera', carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
                      vehicle, {}, display_pos=[0, 1])
        SensorManager(world, display_manager, 'RGBCamera', carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+90)),
                      vehicle, {}, display_pos=[0, 2])
        # SensorManager(world, display_manager, 'RGBCamera', carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=180)),
        #               vehicle, {}, display_pos=[1, 1])

        # SensorManager(world, display_manager, 'LiDAR', carla.Transform(carla.Location(x=0, z=2.4)),
        #              vehicle, {'channels' : '64', 'range' : '100',  'points_per_second': '250000', 'rotation_frequency': '20'}, display_pos=[1, 0])
        SensorManager(world, display_manager, 'DepthCamera',
                      carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
                      vehicle, {'fov': '90'}, display_pos=[1, 0])  # 深度相机
        SensorManager(world, display_manager, 'InstanceSegmentationCamera',
                      carla.Transform(carla.Location(x=0, z=2.4), carla.Rotation(yaw=+00)),
                      vehicle, {'fov': '90'}, display_pos=[1, 1])  # 实例分割相机
        SensorManager(world, display_manager, 'SemanticLiDAR', carla.Transform(carla.Location(x=0, z=2.4)),
                      vehicle,
                      {'channels': '64', 'range': '100', 'points_per_second': '100000', 'rotation_frequency': '20'},
                      display_pos=[1, 2])  # 语义雷达

        # 仿真循环
        call_exit = False
        time_init_sim = timer.time()
        while True:
            # Carla Tick
            if args.sync:
                world.tick()
            else:
                world.wait_for_tick()

            # Render received data
            display_manager.render()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    call_exit = True
                elif event.type == pygame.KEYDOWN:
                    if event.key == K_ESCAPE or event.key == K_q:
                        call_exit = True
                        break

            if call_exit:
                break

    finally:
        if display_manager:
            display_manager.destroy()

        client.apply_batch([carla.command.DestroyActor(x) for x in vehicle_list])

        world.apply_settings(original_settings)



def main():
    argparser = argparse.ArgumentParser(
        description='CARLA Sensor tutorial')
    argparser.add_argument(
        '--host',
        metavar='H',
        default='127.0.0.1',
        help='IP of the host server (default: 127.0.0.1)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port to listen to (default: 2000)')
    argparser.add_argument(
        '--sync',
        action='store_true',
        help='Synchronous mode execution')
    argparser.add_argument(
        '--async',
        dest='sync',
        action='store_false',
        help='Asynchronous mode execution')
    argparser.set_defaults(sync=True)
    argparser.add_argument(
        '--res',
        metavar='WIDTHxHEIGHT',
        default='1280x720',
        help='window resolution (default: 1280x720)')

    args = argparser.parse_args()

    args.width, args.height = [int(x) for x in args.res.split('x')]

    try:
        client = carla.Client(args.host, args.port)
        client.set_timeout(5.0)

        run_simulation(args, client)

    except KeyboardInterrupt:
        print('\nCancelled by user. Bye!')


if __name__ == '__main__':

    main()
