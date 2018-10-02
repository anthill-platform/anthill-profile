CREATE TABLE `gamespace_access` (
  `gamespace_id` int(11) NOT NULL,
  `access_private` mediumtext NOT NULL,
  `access_protected` mediumtext NOT NULL,
  `access_public` mediumtext NOT NULL,
  PRIMARY KEY (`gamespace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;