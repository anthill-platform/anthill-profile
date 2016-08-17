CREATE TABLE `account_profiles` (
  `account_id` int(11) NOT NULL,
  `gamespace_id` int(11) NOT NULL,
  `payload` json DEFAULT NULL,
  PRIMARY KEY (`account_id`,`gamespace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;