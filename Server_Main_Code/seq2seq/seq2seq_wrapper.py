########## PART 3 - TRAINING THE SEQ2SEQ MODEL ##########

import tensorflow as tf
import numpy as np
import sys


class Seq2Seq(object):

    def __init__(self, xseq_len, yseq_len,
            xvocab_size, yvocab_size,
            emb_dim, num_layers, ckpt_path,
            lr=0.0001,
            epochs=100000, model_name='seq2seq_model'):

        #Инициализация свойств класса
        self.xseq_len = xseq_len
        self.yseq_len = yseq_len
        self.ckpt_path = ckpt_path
        self.epochs = epochs
        self.model_name = model_name


        # Построение графа вычислений
        def __graph__():

            #Создание тензоров формата(placeholder)
            tf.reset_default_graph()
            #Placeholder для входных данных : лист индексов длины xseq_len
            self.enc_ip = [ tf.placeholder(shape=[None,],
                            dtype=tf.int64,
                            name='ei_{}'.format(t)) for t in range(xseq_len) ]

            #Placeholder для правильных выходных данных : лист индексов длины yseq_len
            self.labels = [ tf.placeholder(shape=[None,],
                            dtype=tf.int64,
                            name='ei_{}'.format(t)) for t in range(yseq_len) ]

            #Специальный формат входной последовательности : 'GO' + [ a_1, a_2, ... a_t-1 ]
            self.dec_ip = [ tf.zeros_like(self.enc_ip[0], dtype=tf.int64, name='GO') ] + self.labels[:-1]

            # Базовая LSTM ячейка с использованием Dropout
            # keep_prob параметр используется для корректировки
            # обучения нейронной сети, вероятность перехода на следующий уровень
            self.keep_prob = tf.placeholder(tf.float32)
            #Создание базовой LSTM ячейки
            basic_cell = tf.nn.rnn_cell.DropoutWrapper(
                    tf.nn.rnn_cell.BasicLSTMCell(emb_dim, state_is_tuple=True),
                    output_keep_prob=self.keep_prob)
            #Создание n слоёв из LSTM ячеек
            stacked_lstm = tf.nn.rnn_cell.MultiRNNCell([basic_cell]*num_layers, state_is_tuple=True)

            #Общий доступ к параметрам между тренировочной и тестовой моделями
            with tf.variable_scope('decoder') as scope:
                # сборка seq2seq модели
                # выходные данные decoder и выходное состояние decoder
                # для этого передаются:
                # encoder входные данные
                # decoder входные данные
                # тип LSTM ячейки, определённый ранее
                # размеры словарей
                # embedding размеры
                self.decode_outputs, self.decode_states = tf.nn.seq2seq.embedding_rnn_seq2seq(self.enc_ip,self.dec_ip, stacked_lstm,
                                                    xvocab_size, yvocab_size, emb_dim)
                # предоставление общего доступа к переменным
                scope.reuse_variables()
                # тестирование модели, где выходные данный предыдущей итерации
                # передаются, как входные данные следующей итерации
                self.decode_outputs_test, self.decode_states_test = tf.nn.seq2seq.embedding_rnn_seq2seq(
                    self.enc_ip, self.dec_ip, stacked_lstm, xvocab_size, yvocab_size,emb_dim,
                    feed_previous=True)

            # Обучение

            # Значение ошибки с изменением весов
            loss_weights = [ tf.ones_like(label, dtype=tf.float32) for label in self.labels ]
            self.loss = tf.nn.seq2seq.sequence_loss(self.decode_outputs, self.labels, loss_weights, yvocab_size)
            # Необходимо минимизировать ошибку
            self.train_op = tf.train.AdamOptimizer(learning_rate=lr).minimize(self.loss)


        # Построение графа
        __graph__()
        sys.stdout.write('\n################Start Chatting Below########################\n')



    '''
        Тренировка и оценка

    '''

    # Получение тензор словаря
    def get_feed(self, X, Y, keep_prob):
        feed_dict = {self.enc_ip[t]: X[t] for t in range(self.xseq_len)}
        feed_dict.update({self.labels[t]: Y[t] for t in range(self.yseq_len)})
        feed_dict[self.keep_prob] = keep_prob # dropout prob
        return feed_dict

    # Тренировка одной подпоследовательности (Batch)
    def train_batch(self, sess, train_batch_gen):
        # Получение следующей подпоследовательности (Batch)
        batchX, batchY = train_batch_gen.__next__()
        # Получение тензор словаря
        feed_dict = self.get_feed(batchX, batchY, keep_prob=0.5)
        _, loss_v = sess.run([self.train_op, self.loss], feed_dict)
        return loss_v

    def eval_step(self, sess, eval_batch_gen):
        # Получение подпоследовательности (Batch)
        batchX, batchY = eval_batch_gen.__next__()
        # Получение тензор словаря
        feed_dict = self.get_feed(batchX, batchY, keep_prob=1.)
        loss_v, dec_op_v = sess.run([self.loss, self.decode_outputs_test], feed_dict)
        # dec_op_v лист, необходимый для транспонирования индексов 0 и 1
        # обмен размера подпоследовательности и размера итерации
        dec_op_v = np.array(dec_op_v).transpose([1,0,2])
        return loss_v, dec_op_v, batchX, batchY

    # оценка 'num_batches' подпоследовательностей (Batches)
    def eval_batches(self, sess, eval_batch_gen, num_batches):
        losses = []
        for i in range(num_batches):
            loss_v, dec_op_v, batchX, batchY = self.eval_step(sess, eval_batch_gen)
            losses.append(loss_v)
        return np.mean(losses)

    #Основная тренировочная функция
    # -запуск тренировочной сессии
    # -периодическая оценка ошибки
    # -вывод статистики обучения
    def train(self, train_set, valid_set, sess=None ):

        # Периодическое сохранение сессии
        saver = tf.train.Saver()

        # Создание сессии, если её ещё нет
        if not sess:
            # Создание сессии
            sess = tf.Session()
            # Инициализация всех переменных
            sess.run(tf.global_variables_initializer())

        sys.stdout.write('\n################Start Chatting Below########################\n')
        # Прогон M эпох
        for i in range(self.epochs):
            try:
                self.train_batch(sess, train_set)
                if i and i% (self.epochs//100) == 0:
                    # Сохранение модели на диск
                    saver.save(sess, self.ckpt_path + self.model_name + '.ckpt', global_step=i)
                    # Оценка и подсчёт ошибки
                    val_loss = self.eval_batches(sess, valid_set, 16)
                    # Вывод статистики
                    print('\nModel saved to disk at iteration #{}'.format(i))
                    print('val   loss : {0:.6f}'.format(val_loss))
                    sys.stdout.flush()
            except KeyboardInterrupt: # Обработка KeyboardInterrupt
                print('Interrupted by user at iteration {}'.format(i))
                self.session = sess
                return sess

    # Восстановление последней сессии
    def restore_last_session(self):
        saver = tf.train.Saver()
        # Создание сессии
        sess = tf.Session()
        # Получение состаяние последней точки остановки
        ckpt = tf.train.get_checkpoint_state(self.ckpt_path)
        # Восстановление сессии
        if ckpt and ckpt.model_checkpoint_path:
            saver.restore(sess, ckpt.model_checkpoint_path)
        return sess

    # prediction
    def predict(self, sess, X):
        feed_dict = {self.enc_ip[t]: X[t] for t in range(self.xseq_len)}
        feed_dict[self.keep_prob] = 1.
        dec_op_v = sess.run(self.decode_outputs_test, feed_dict)
        # dec_op_v лист, необходимый для транспонирования индексов 0 и 1
        # обмен размера подпоследовательности и размера итерации
        dec_op_v = np.array(dec_op_v).transpose([1,0,2])
        # Возвращение индекса с самой высокой вероятностью
        return np.argmax(dec_op_v, axis=2)

