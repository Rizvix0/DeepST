
# coding: utf-8

# In[1]:



"""
Usage:
    THEANO_FLAGS="device=gpu0" python exptBasestationXIAN.py
"""
from __future__ import print_function
import sys
sys.path.insert(0, '..')
import os
import pickle
import numpy as np
import math
import h5py

from keras.optimizers import Adam
from keras.callbacks import EarlyStopping, ModelCheckpoint
from deepst.models.STResNet import stresnet
from deepst.config import Config
import deepst.metrics as metrics
from deepst.datasets import ShenyangRegular, DalianRegular
np.random.seed(1337)  # for reproducibility
import tensorflow as tf
from keras.backend.tensorflow_backend import set_session
from keras import backend
config = tf.ConfigProto()
config.gpu_options.allow_growth = True

set_session(tf.Session(config=config))
# parameters
# data path, you may set your own data path with the global envirmental
# variable DATAPATH
DATAPATH = Config().DATAPATH
nb_epoch = 500  # number of epoch at training stage
nb_epoch_cont = 100  # number of epoch at training (cont) stage
batch_size = 32  # batch size
T = 48  # number of time intervals in one day
nbfilter=64
lr_arr = [0.002, 0.005]  # learning rate
# lr_arr = [0.002]
len_closeness = 3  # length of closeness dependent sequence
len_period = 1  # length of peroid dependent sequence
len_trend = 1  # length of trend dependent sequence
nb_residual_unit = 4   # number of residual units

nb_flow = 2  # there are two types of flows: new-flow and end-flow
# divide data into two subsets: Train & Test, of which the test set is the
# last 10 days
days_test = 4
len_test = T * days_test
map_height, map_width = 8, 8  # grid size
# For NYC Bike data, there are 81 available grid-based areas, each of
# which includes at least ONE bike station. Therefore, we modify the final
# RMSE by multiplying the following factor (i.e., factor).
nb_area = 8 * 8
m_factor = math.sqrt(1. * map_height * map_width / nb_area)
print('factor: ', m_factor)
path_result = 'RET'
path_model = 'MODEL'

if os.path.isdir(path_result) is False:
    os.mkdir(path_result)
if os.path.isdir(path_model) is False:
    os.mkdir(path_model)


# In[2]:


def build_model(external_dim, lr, nbfilter=64):
    c_conf = (len_closeness, nb_flow, map_height,
              map_width) if len_closeness > 0 else None
    p_conf = (len_period, nb_flow, map_height,
              map_width) if len_period > 0 else None
    t_conf = (len_trend, nb_flow, map_height,
              map_width) if len_trend > 0 else None

    model = stresnet(c_conf=c_conf, p_conf=p_conf, t_conf=t_conf,
                     external_dim=external_dim, nb_residual_unit=nb_residual_unit, nbfilter=nbfilter)
    adam = Adam(lr=lr)
    model.compile(loss='mse', optimizer=adam, metrics=[metrics.rmse])
    model.summary()
    # from keras.utils.visualize_util import plot
    # plot(model, to_file='model.png', show_shapes=True)
    return model


def main(lr):
    # load data
    print("loading data...")
    X_train, Y_train, X_test, Y_test, mmn, external_dim, timestamp_train, timestamp_test = DalianRegular.load_data(
        T=T, nb_flow=nb_flow, len_closeness=len_closeness, len_period=len_period, len_trend=len_trend, len_test=len_test,
        preprocess_name='preprocessing.pkl', meta_data=False)

    print("\n days (test): ", [v[:8] for v in timestamp_test[0::T]])

    print('=' * 10)
    print("compiling model...")
    print(
        "**at the first time, it takes a few minites to compile if you use [Theano] as the backend**")
    print("before build_model")
    model = build_model(external_dim, lr, nbfilter=nbfilter)
    print("after build_model")
    hyperparams_name = 'c{}.p{}.t{}.resunit{}.lr{}'.format(
        len_closeness, len_period, len_trend, nb_residual_unit, lr)
    fname_param = os.path.join('MODEL', '{}.best.h5'.format(hyperparams_name))

    early_stopping = EarlyStopping(monitor='val_rmse', patience=5, mode='min')
    model_checkpoint = ModelCheckpoint(
        fname_param, monitor='val_rmse', verbose=0, save_best_only=True, mode='min')

    print('=' * 10)
    print("training model...")
    history = model.fit(X_train, Y_train,
                        nb_epoch=nb_epoch,
                        batch_size=batch_size,
                        validation_split=0.143,
                        callbacks=[early_stopping, model_checkpoint],
                        verbose=0)
    model.save_weights(os.path.join(
        'MODEL', '{}.h5'.format(hyperparams_name)), overwrite=True)
    pickle.dump((history.history), open(os.path.join(
        path_result, '{}.history.pkl'.format(hyperparams_name)), 'wb'))

    print('=' * 10)
    print('evaluating using the model that has the best loss on the valid set')

    model.load_weights(fname_param)
    score = model.evaluate(X_train, Y_train, batch_size=Y_train.shape[
                           0] // 48, verbose=0)
    print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
          (score[0], score[1], score[1] * (mmn._max - mmn._min) * m_factor))

    score = model.evaluate(
        X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
    print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
          (score[0], score[1], score[1] * (mmn._max - mmn._min) * m_factor))

    # Y_pred = model.predict(X_test, batch_size=Y_test.shape[0], verbose=0)
    # Y_pred = mmn.inverse_transform(Y_pred)
    # Y_test = mmn.inverse_transform(Y_test)
    # Y_test = np.reshape(Y_test, (Y_test.shape[0] * Y_test.shape[1] * Y_test.shape[2] * Y_test.shape[3],))
    # Y_pred = np.reshape(Y_pred, (Y_pred.shape[0] * Y_pred.shape[1] * Y_pred.shape[2] * Y_pred.shape[3],))
    # print(math.sqrt(np.mean((Y_pred - Y_test)**2)))
    # Y_pred = Y_pred[Y_test>20]
    # Y_test = Y_test[Y_test>20]
    # print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
    #       (score[0], score[1], score[1] * (mmn._max - mmn._min) * m_factor))
    # print('mape: {0} {1}'.format(math.sqrt(np.mean((Y_pred - Y_test)**2)), np.mean( abs(Y_pred - Y_test)/Y_test)))
    print('=' * 10)
    print("training model (cont)...")
    fname_param = os.path.join(
        'MODEL', '{}.cont.best.h5'.format(hyperparams_name))
    model_checkpoint = ModelCheckpoint(
        fname_param, monitor='rmse', verbose=0, save_best_only=True, mode='min')
    history = model.fit(X_train, Y_train, nb_epoch=nb_epoch_cont, verbose=0, batch_size=batch_size, callbacks=[
                        model_checkpoint], validation_data=(X_test, Y_test))
    pickle.dump((history.history), open(os.path.join(
        path_result, '{}.cont.history.pkl'.format(hyperparams_name)), 'wb'))
    model.save_weights(os.path.join(
        'MODEL', '{}_cont.h5'.format(hyperparams_name)), overwrite=True)

    print('=' * 10)
    print('evaluating using the final model')

    score = model.evaluate(X_train, Y_train, batch_size=Y_train.shape[
                           0] // 48, verbose=0)
    print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
          (score[0], score[1], score[1] * (mmn._max - mmn._min) * m_factor))

    score2 = model.predict(X_test, batch_size=Y_test.shape[0], verbose=0)
    file_temp = h5py.File("prediction", "w")
    file_temp.create_dataset("prediction", data=score2)
    file_temp.create_dataset("real", data=Y_test)
    score = model.evaluate(
        X_test, Y_test, batch_size=Y_test.shape[0], verbose=1)


    # print(Y_test.shape)
    # print(Y_pred.shape)

    print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
          (score[0], score[1], score[1] * (mmn._max - mmn._min) * m_factor))
    # print('mape: {0}'.format(np.mean((Y_pred - Y_test)/Y_test)))

if __name__ == '__main__':
    for lr_value in lr_arr:
        main(lr_value)
        backend.clear_session()



